from collections import Counter
from dataclasses import replace
from unittest.mock import MagicMock

from app.config import Settings
from app.email_handler import Outcome
from app.server import create_app


def make_client(results: Counter | None = None):
    settings = replace(Settings.from_env(), pubsub_oidc_audience=None)  # auth disabled, as in local dev
    handler = MagicMock()
    handler.process_pending.return_value = results if results is not None else Counter()
    gmail = MagicMock()
    gmail.start_watch.return_value = {"historyId": "1", "expiration": "2"}
    return create_app(settings, handler, gmail, kb_size=42).test_client(), handler, gmail


def test_health_reports_ok():
    client, _, _ = make_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "knowledge_chunks": 42}


def test_push_runs_the_handler_and_returns_summary():
    client, handler, _ = make_client(Counter({Outcome.SENT: 2}))
    response = client.post("/pubsub/push", json={"message": {"data": "e30="}})
    assert response.status_code == 200
    assert response.get_json() == {"sent": 2}
    handler.process_pending.assert_called_once()


def test_push_returns_500_when_an_email_failed_so_pubsub_retries():
    client, _, _ = make_client(Counter({Outcome.FAILED: 1}))
    assert client.post("/pubsub/push", json={}).status_code == 500


def test_renew_watch_calls_gmail():
    client, _, gmail = make_client()
    assert client.post("/admin/renew-watch").status_code == 200
    gmail.start_watch.assert_called_once()


def test_push_rejects_missing_token_when_auth_enabled():
    settings = replace(Settings.from_env(), pubsub_oidc_audience="https://service.example")
    app = create_app(settings, MagicMock(), MagicMock(), kb_size=1)
    assert app.test_client().post("/pubsub/push", json={}).status_code == 401
