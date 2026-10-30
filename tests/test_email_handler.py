"""EmailHandler pipeline tests using fakes, so no network or credentials are needed.  Run: pytest"""
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.email_handler import EmailHandler, Outcome
from app.models import Category, Classification, Evidence, IncomingEmail


def make_settings(send_mode="draft") -> Settings:
    return replace(Settings.from_env(), send_mode=send_mode, support_address="support@example.com")


def make_email(**overrides) -> IncomingEmail:
    fields = dict(
        message_id="m1",
        thread_id="t1",
        rfc_message_id="<abc@mail>",
        sender="Jan Novak <jan@example.com>",
        reply_to="jan@example.com",
        subject="Error ERR-101",
        body="My Pulsar-1 shows ERR-101, what now?",
    )
    fields.update(overrides)
    return IncomingEmail(**fields)


def make_classification(category=Category.TECHNICAL_SUPPORT, needs_kb=True) -> Classification:
    return Classification(
        category=category,
        needs_knowledge_base=needs_kb,
        search_query="ERR-101",
        summary="Customer reports ERR-101",
        language="English",
    )


@pytest.fixture
def agent():
    mock = MagicMock()
    mock.classify.return_value = make_classification()
    mock.search_knowledge_base.return_value = [Evidence("manual.pdf", "ERR-101 means ...", 0.9)]
    mock.draft_reply.return_value = "Hello Jan, ..."
    return mock


@pytest.fixture
def gmail():
    return MagicMock()


def test_technical_email_is_answered_with_evidence_and_sent(agent, gmail):
    handler = EmailHandler(agent, gmail, make_settings(send_mode="send"))

    outcome = handler.handle(make_email())

    assert outcome == Outcome.SENT
    agent.search_knowledge_base.assert_called_once_with("ERR-101")
    reply = gmail.send_reply.call_args.args[0]
    assert reply.to == "jan@example.com"
    assert reply.subject == "Re: Error ERR-101"
    assert reply.in_reply_to == "<abc@mail>"
    gmail.mark_processed.assert_called_once_with("m1")


def test_draft_mode_saves_draft_instead_of_sending(agent, gmail):
    outcome = EmailHandler(agent, gmail, make_settings(send_mode="draft")).handle(make_email())

    assert outcome == Outcome.DRAFTED
    gmail.save_draft.assert_called_once()
    gmail.send_reply.assert_not_called()


def test_knowledge_base_is_skipped_when_not_needed(agent, gmail):
    agent.classify.return_value = make_classification(Category.GENERAL, needs_kb=False)

    EmailHandler(agent, gmail, make_settings()).handle(make_email(subject="Thanks!"))

    agent.search_knowledge_base.assert_not_called()


def test_every_category_gets_a_reply(agent, gmail):
    agent.classify.return_value = make_classification(Category.OTHER, needs_kb=False)

    outcome = EmailHandler(agent, gmail, make_settings(send_mode="send")).handle(make_email(subject="Refund!"))

    assert outcome == Outcome.SENT
    agent.draft_reply.assert_called_once()
    gmail.send_reply.assert_called_once()


@pytest.mark.parametrize(
    "overrides",
    [
        {"sender": "Support <support@example.com>"},
        {"sender": "noreply@shop.com"},
        {"headers": {"auto-submitted": "auto-replied"}},
        {"headers": {"precedence": "bulk"}},
        {"headers": {"list-unsubscribe": "<mailto:x@y.z>"}},
    ],
)
def test_automated_mail_never_reaches_the_model(agent, gmail, overrides):
    outcome = EmailHandler(agent, gmail, make_settings(send_mode="send")).handle(make_email(**overrides))

    assert outcome == Outcome.SKIPPED
    agent.classify.assert_not_called()
    gmail.send_reply.assert_not_called()


def test_failed_email_stays_pending_and_does_not_block_others(agent, gmail):
    gmail.list_pending_ids.return_value = ["bad", "good"]
    gmail.fetch_email.side_effect = [RuntimeError("boom"), make_email(message_id="good")]

    results = EmailHandler(agent, gmail, make_settings()).process_pending()

    assert results[Outcome.FAILED] == 1
    assert results[Outcome.DRAFTED] == 1
    gmail.mark_processed.assert_called_once_with("good")
