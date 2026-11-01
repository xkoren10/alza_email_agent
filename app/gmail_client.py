"""Thin wrapper around the Gmail API: list, read, label, draft and send.

Replaces the former IMAP/SMTP code. The Gmail API is required for push
notifications (`users.watch` -> Pub/Sub); IMAP cannot do that.
"""
import base64
import html
import logging
import re
from email.message import EmailMessage, Message
from email.utils import parseaddr

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.attachments import enforce_total_size, validate_attachment
from app.config import Settings
from app.models import IncomingEmail, Reply

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]  # read, label, draft and send (no delete)
TOKEN_URI = "https://oauth2.googleapis.com/token"
RETRIES = 3
LOOKBACK = "2d"  # never touch mail older than this, so a first run cannot answer the whole inbox


class GmailClient:
    def __init__(self, settings: Settings):
        credentials = Credentials(
            token=None,
            refresh_token=settings.gmail_refresh_token,
            client_id=settings.gmail_client_id,
            client_secret=settings.gmail_client_secret,
            token_uri=TOKEN_URI,
            scopes=SCOPES,
        )
        self._service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        self._user = settings.gmail_user
        self._topic = settings.pubsub_topic
        self._processed_label = settings.processed_label
        self._label_ids: dict[str, str] = {}

    # ------------------------------------------------------------------ push notifications

    def start_watch(self) -> dict:
        """Asks Gmail to publish a Pub/Sub message whenever the INBOX changes. Expires after 7 days."""
        body = {"topicName": self._topic, "labelIds": ["INBOX"], "labelFilterBehavior": "INCLUDE"}
        return self._service.users().watch(userId=self._user, body=body).execute(num_retries=RETRIES)

    # ------------------------------------------------------------------ reading

    def list_pending_ids(self, limit: int) -> list[str]:
        """Inbox messages we have not handled yet (oldest first)."""
        query = f"in:inbox newer_than:{LOOKBACK} -label:{self._processed_label}"
        result = (
            self._service.users()
            .messages()
            .list(userId=self._user, q=query, maxResults=limit)
            .execute(num_retries=RETRIES)
        )
        return [m["id"] for m in reversed(result.get("messages", []))]

    def fetch_email(self, message_id: str) -> IncomingEmail:
        message = (
            self._service.users()
            .messages()
            .get(userId=self._user, id=message_id, format="full")
            .execute(num_retries=RETRIES)
        )
        payload = message["payload"]
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        plain, html_text, attachments = self._walk_parts(message_id, payload)

        sender = headers.get("from", "")
        return IncomingEmail(
            message_id=message_id,
            thread_id=message["threadId"],
            rfc_message_id=headers.get("message-id", ""),
            sender=sender,
            reply_to=parseaddr(headers.get("reply-to") or sender)[1],
            subject=headers.get("subject", "(no subject)"),
            body=plain or self._html_to_text(html_text),
            headers=headers,
            attachments=enforce_total_size(attachments),
        )

    def _walk_parts(self, message_id: str, part: dict) -> tuple[str, str, list]:
        """Collects the plain-text body, the HTML body and all valid attachments from a MIME tree."""
        plain, html_text, attachments = "", "", []
        stack = [part]
        while stack:
            current = stack.pop(0)
            stack = current.get("parts", []) + stack  # depth-first, keeps document order
            mime, filename, body = current.get("mimeType", ""), current.get("filename", ""), current.get("body", {})

            # In app/gmail_client.py, inside _walk_pers():
            if filename or ((mime.startswith("image/") or mime.startswith("audio/")) and body.get("attachmentId")):
                filename = filename or f"inline.{mime.split('/')[-1]}"
                attachment = validate_attachment(filename, self._attachment_bytes(message_id, body))
                if attachment:
                    attachments.append(attachment)
            elif mime == "text/plain" and not plain:
                plain = self._decode_text(current)
            elif mime == "text/html" and not html_text:
                html_text = self._decode_text(current)
        return plain, html_text, attachments

    def _attachment_bytes(self, message_id: str, body: dict) -> bytes | None:
        if "data" in body:
            return base64.urlsafe_b64decode(body["data"])
        if "attachmentId" in body:
            result = (
                self._service.users()
                .messages()
                .attachments()
                .get(userId=self._user, messageId=message_id, id=body["attachmentId"])
                .execute(num_retries=RETRIES)
            )
            return base64.urlsafe_b64decode(result["data"])
        return None

    @staticmethod
    def _decode_text(part: dict) -> str:
        raw = base64.urlsafe_b64decode(part.get("body", {}).get("data", ""))
        content_type = next(
            (h["value"] for h in part.get("headers", []) if h["name"].lower() == "content-type"), "text/plain"
        )
        probe = Message()
        probe["Content-Type"] = content_type
        return raw.decode(probe.get_content_charset() or "utf-8", errors="replace")

    @staticmethod
    def _html_to_text(markup: str) -> str:
        text = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
        text = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", text)
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    # ------------------------------------------------------------------ writing

    def save_draft(self, reply: Reply) -> str:
        draft = (
            self._service.users()
            .drafts()
            .create(userId=self._user, body={"message": self._build_message(reply)})
            .execute(num_retries=RETRIES)
        )
        return draft["id"]

    def send_reply(self, reply: Reply) -> str:
        sent = (
            self._service.users()
            .messages()
            .send(userId=self._user, body=self._build_message(reply))
            .execute(num_retries=RETRIES)
        )
        return sent["id"]

    @staticmethod
    def _build_message(reply: Reply) -> dict:
        msg = EmailMessage()
        msg["To"] = reply.to
        msg["Subject"] = reply.subject
        if reply.in_reply_to:
            msg["In-Reply-To"] = reply.in_reply_to
            msg["References"] = reply.in_reply_to
        msg.set_content(reply.body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return {"raw": raw, "threadId": reply.thread_id}

    # ------------------------------------------------------------------ labels

    def mark_processed(self, message_id: str) -> None:
        self._add_label(message_id, self._processed_label)

    def _add_label(self, message_id: str, label_name: str) -> None:
        self._service.users().messages().modify(
            userId=self._user, id=message_id, body={"addLabelIds": [self._label_id(label_name)]}
        ).execute(num_retries=RETRIES)

    def _label_id(self, name: str) -> str:
        """Returns the id of a label, creating it on first use."""
        if not self._label_ids:
            existing = self._service.users().labels().list(userId=self._user).execute(num_retries=RETRIES)
            self._label_ids = {label["name"]: label["id"] for label in existing.get("labels", [])}
        if name not in self._label_ids:
            created = (
                self._service.users()
                .labels()
                .create(userId=self._user, body={"name": name})
                .execute(num_retries=RETRIES)
            )
            self._label_ids[name] = created["id"]
        return self._label_ids[name]
