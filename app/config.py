"""Central configuration. Every setting comes from an environment variable.

On GCP the values are injected by Cloud Run (secrets via Secret Manager);
locally they are read from a `.env` file (see `.env.example`).
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    # --- Gemini ---
    gemini_model: str
    gemini_api_key: str | None
    gemini_use_vertex: bool  # True -> authenticate with the Cloud Run service account instead of an API key
    gcp_project: str | None
    gcp_location: str

    # --- Gmail API (OAuth refresh token of the support mailbox) ---
    gmail_client_id: str | None
    gmail_client_secret: str | None
    gmail_refresh_token: str | None
    gmail_user: str  # "me" = the authenticated mailbox
    support_address: str  # used to detect and ignore our own messages

    # --- Pub/Sub ---
    pubsub_topic: str | None  # projects/<project>/topics/<topic>, used when (re)creating the Gmail watch
    pubsub_oidc_audience: str | None  # if set, push requests must carry a Google OIDC token for this audience
    pubsub_oidc_service_account: str | None  # expected service account of the push subscription / scheduler

    # --- Behaviour ---
    send_mode: str  # "send" = reply to the customer, "draft" = only save a Gmail draft for human review
    processed_label: str
    max_emails_per_run: int

    # --- Knowledge base ---
    index_dir: Path
    top_k: int
    embedding_model: str
    embedding_dimensions: int  # must match the index built by scripts/create_indices.py

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            gemini_use_vertex=_flag("GEMINI_USE_VERTEX"),
            gcp_project=os.getenv("GCP_PROJECT"),
            gcp_location=os.getenv("GCP_LOCATION", "europe-west1"),
            gmail_client_id=os.getenv("GMAIL_CLIENT_ID"),
            gmail_client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
            gmail_refresh_token=os.getenv("GMAIL_REFRESH_TOKEN"),
            gmail_user=os.getenv("GMAIL_USER", "me"),
            support_address=os.getenv("SUPPORT_ADDRESS", "").lower(),
            pubsub_topic=os.getenv("PUBSUB_TOPIC"),
            pubsub_oidc_audience=os.getenv("PUBSUB_OIDC_AUDIENCE"),
            pubsub_oidc_service_account=os.getenv("PUBSUB_OIDC_SERVICE_ACCOUNT"),
            send_mode=os.getenv("SEND_MODE", "draft").lower(),
            processed_label=os.getenv("PROCESSED_LABEL", "alza-ai-processed"),
            max_emails_per_run=int(os.getenv("MAX_EMAILS_PER_RUN", "10")),
            index_dir=Path(os.getenv("INDEX_DIR", PROJECT_ROOT / "knowledge_base" / "vector_index")),
            top_k=int(os.getenv("KB_TOP_K", "3")),
            embedding_model=os.getenv("EMBEDDING_MODEL", "gemini-embedding-001"),
            embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "768")),
        )
