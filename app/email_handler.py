"""Turns one incoming email into a reply: classify -> gather evidence -> draft -> send."""
import logging
import threading
from collections import Counter
from email.utils import parseaddr
from enum import Enum

from app.agent import SupportAgent
from app.config import Settings
from app.gmail_client import GmailClient
from app.models import IncomingEmail, Reply

log = logging.getLogger(__name__)

AUTOMATED_SENDER_PARTS = ("noreply", "no-reply", "donotreply", "mailer-daemon", "postmaster")


class Outcome(str, Enum):
    SKIPPED = "skipped"  # automated mail or our own message, ignored
    DRAFTED = "drafted"  # reply saved as a Gmail draft
    SENT = "sent"  # reply sent to the customer
    FAILED = "failed"


class EmailHandler:
    def __init__(self, agent: SupportAgent, gmail: GmailClient, settings: Settings):
        self._agent = agent
        self._gmail = gmail
        self._settings = settings
        self._lock = threading.Lock()  # Pub/Sub can deliver notifications concurrently; handle one batch at a time

    # ------------------------------------------------------------------ entry points

    def process_pending(self) -> Counter:
        """Handles every unprocessed inbox email. Called whenever a Pub/Sub notification arrives."""
        results: Counter = Counter()
        with self._lock:
            for message_id in self._gmail.list_pending_ids(self._settings.max_emails_per_run):
                try:
                    email = self._gmail.fetch_email(message_id)
                    results[self.handle(email)] += 1
                except Exception:
                    log.exception("Failed to process message %s", message_id)
                    results[Outcome.FAILED] += 1
        return results

    def handle(self, email: IncomingEmail) -> Outcome:
        """Runs the full pipeline for one email and records the result in Gmail."""
        log.info("Handling email %s from %s: %s, %d attachments", email.message_id, email.sender, email.subject, len(email.attachments))

        if self._is_automated(email):
            log.info("Skipping automated or own message %s", email.message_id)
            self._gmail.mark_processed(email.message_id)
            return Outcome.SKIPPED

        classification = self._agent.classify(email)
        log.info("Classified as %s: %s", classification.category.value, classification.summary)

        evidence = []
        if classification.needs_knowledge_base:
            query = classification.search_query or f"{email.subject}\n{email.body}"
            evidence = self._agent.search_knowledge_base(query)
            log.info("Gathered %d knowledge base extracts", len(evidence))

        reply = Reply(
            to=email.reply_to,
            subject=self._reply_subject(email.subject),
            body=self._agent.draft_reply(email, classification, evidence),
            thread_id=email.thread_id,
            in_reply_to=email.rfc_message_id,
        )

        if self._settings.send_mode == "send":
            self._gmail.send_reply(reply)
            outcome = Outcome.SENT
        else:
            self._gmail.save_draft(reply)
            outcome = Outcome.DRAFTED

        # Labelled last: if anything above fails, the email stays pending and Pub/Sub retries it.
        self._gmail.mark_processed(email.message_id)
        log.info("Email %s: %s", email.message_id, outcome.value)
        return outcome

    # ------------------------------------------------------------------ helpers

    def _is_automated(self, email: IncomingEmail) -> bool:
        """Guards against auto-reply loops with other robots (and with ourselves)."""
        address = parseaddr(email.sender)[1].lower()
        headers = email.headers
        return (
            address == self._settings.support_address
            or any(part in address for part in AUTOMATED_SENDER_PARTS)
            or headers.get("auto-submitted", "no").lower() != "no"
            or headers.get("precedence", "").lower() in {"bulk", "list", "junk"}
            or "list-unsubscribe" in headers
        )

    @staticmethod
    def _reply_subject(subject: str) -> str:
        return subject if subject.lower().startswith("re:") else f"Re: {subject}"
