"""Validation of customer attachments before they are shown to the model.

Attachments are kept in memory and never written to disk, so there is no
path-traversal surface. Three checks remain: extension whitelist, size limit
and magic-byte verification (prevents a renamed executable posing as a PDF).
"""
import logging
import os

from app.models import Attachment

log = logging.getLogger(__name__)

# Gemini accepts at most ~20 MB per request when files are sent inline.
MAX_FILE_SIZE_MB = 10
MAX_TOTAL_SIZE_MB = 18

# extension -> (mime type, accepted file signatures)
SUPPORTED_FILE_TYPES: dict[str, tuple[str, list[bytes]]] = {
    ".pdf": ("application/pdf", [b"%PDF"]),
    ".png": ("image/png", [b"\x89PNG\r\n\x1a\n"]),
    ".jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".webp": ("image/webp", []),  # RIFF....WEBP, checked separately
    ".gif": ("image/gif", [b"GIF87a", b"GIF89a"]),
    ".mp3": ("audio/mpeg", [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"]),
    ".wav": ("audio/wav", []),  # RIFF....WAVE, checked separately
    ".m4a": ("audio/mp4", []),  # ....ftyp, checked separately
}


def _matches_signature(data: bytes, ext: str) -> bool:
    if ext == ".webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if ext == ".wav":
        return data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    if ext == ".m4a":
        return data[4:8] == b"ftyp"
    return any(data.startswith(sig) for sig in SUPPORTED_FILE_TYPES[ext][1])


def validate_attachment(filename: str, data: bytes | None) -> Attachment | None:
    """Returns an Attachment if the file passes every check, otherwise None."""
    ext = os.path.splitext(filename)[1].lower()

    if ext not in SUPPORTED_FILE_TYPES:
        log.warning("Blocked unsupported file type: %s", filename)
        return None
    if not data:
        return None
    if len(data) > MAX_FILE_SIZE_MB * 1024 * 1024:
        log.warning("Blocked oversized file (%.1f MB): %s", len(data) / 1024 / 1024, filename)
        return None
    if not _matches_signature(data, ext):
        log.warning("Blocked file whose content does not match its extension: %s", filename)
        return None

    return Attachment(filename=os.path.basename(filename), mime_type=SUPPORTED_FILE_TYPES[ext][0], data=data)


def enforce_total_size(attachments: list[Attachment]) -> list[Attachment]:
    """Keeps attachments (in order) until the total size would exceed the request limit."""
    kept, total = [], 0
    for att in attachments:
        total += len(att.data)
        if total > MAX_TOTAL_SIZE_MB * 1024 * 1024:
            log.warning("Dropping %s: total attachment size limit reached", att.filename)
            continue
        kept.append(att)
    return kept
