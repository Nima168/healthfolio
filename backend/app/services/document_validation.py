"""Upload validation: file type from content, and safe display names (api_contract_spec.md Section 6.1.2)."""

import re
import unicodedata

# Signature → media type. The type is decided only from the file's first bytes.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)
SNIFF_BYTES = 8

DEFAULT_EXTENSION = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}

_CONTROL_OR_SEPARATOR = re.compile(r"[\x00-\x1f\x7f/\\]")


def detect_media_type(head: bytes) -> str | None:
    """Return the media type for supported content, or None."""
    for signature, media_type in _SIGNATURES:
        if head.startswith(signature):
            return media_type
    return None


def sanitise_filename(name: str | None, media_type: str) -> str:
    """A display name only: never used as a storage path."""
    raw = unicodedata.normalize("NFC", name or "")
    base = re.split(r"[\\/]", raw)[-1]  # drop any directory part, Windows or POSIX
    base = _CONTROL_OR_SEPARATOR.sub("", base).strip().strip(".")
    if not base:
        base = "document" + DEFAULT_EXTENSION[media_type]
    if len(base) > 255:
        stem, dot, extension = base.rpartition(".")
        base = (stem[: 255 - len(extension) - 1] + dot + extension) if dot and len(extension) <= 10 else base[:255]
    return base
