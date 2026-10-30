"""Flask app exposed on Cloud Run.

    GET  /health            liveness / readiness probe
    POST /pubsub/push       receives Gmail notifications forwarded by a Pub/Sub push subscription
    POST /admin/renew-watch re-registers the Gmail watch (called daily by Cloud Scheduler)
"""
import base64
import json
import logging

from flask import Flask, jsonify, request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import Settings
from app.email_handler import EmailHandler, Outcome
from app.gmail_client import GmailClient

log = logging.getLogger(__name__)


def create_app(settings: Settings, handler: EmailHandler, gmail: GmailClient, kb_size: int) -> Flask:
    app = Flask(__name__)

    def caller_is_authorised() -> bool:
        """Checks the Google-signed OIDC token that Pub/Sub / Cloud Scheduler attach to their requests.

        Skipped (with a warning) when PUBSUB_OIDC_AUDIENCE is not set, i.e. in local development.
        Cloud Run's own IAM check (--no-allow-unauthenticated) should stay on as the first line of defence.
        """
        if not settings.pubsub_oidc_audience:
            log.warning("PUBSUB_OIDC_AUDIENCE not set: request authentication is disabled")
            return True
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        try:
            claims = id_token.verify_oauth2_token(
                header.removeprefix("Bearer "), google_requests.Request(), settings.pubsub_oidc_audience
            )
        except ValueError:
            return False
        expected = settings.pubsub_oidc_service_account
        return bool(claims.get("email_verified")) and (not expected or claims.get("email") == expected)

    @app.get("/health")
    def health():
        return jsonify(status="ok", knowledge_chunks=kb_size)

    @app.post("/pubsub/push")
    def receive_email_notification():
        if not caller_is_authorised():
            return jsonify(error="unauthorised"), 401

        # The notification only says "the mailbox changed" ({emailAddress, historyId}); the handler
        # looks for unprocessed mail itself, which also makes duplicate deliveries harmless.
        log.info("Pub/Sub notification: %s", _decode_notification(request.get_json(silent=True)))

        results = handler.process_pending()
        summary = {outcome.value: count for outcome, count in results.items()}
        if results[Outcome.FAILED]:
            # Non-2xx makes Pub/Sub redeliver; emails that already succeeded are labelled and not repeated.
            return jsonify(summary), 500
        return jsonify(summary), 200

    @app.post("/admin/renew-watch")
    def renew_watch():
        if not caller_is_authorised():
            return jsonify(error="unauthorised"), 401
        result = gmail.start_watch()
        log.info("Gmail watch renewed: %s", result)
        return jsonify(result), 200

    return app


def _decode_notification(envelope: dict | None) -> dict:
    """Best-effort decoding of the Pub/Sub envelope, for logging only."""
    try:
        return json.loads(base64.b64decode(envelope["message"]["data"]))
    except (TypeError, KeyError, ValueError):
        return {}
