"""Email delivery behind a replaceable interface (backend_spec.md Section 2.1).

Emails never contain medical information. Message bodies and links are never logged.
"""

import logging
import uuid
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """Delivery failed; the caller records the failure category."""


class EmailSender(Protocol):
    provider: str

    def send(self, to: str, subject: str, body: str) -> str:
        """Send a plain-text email and return a provider message ID."""
        ...


class FileEmailSender:
    """Development/test sender: writes each email as an .eml file instead of sending it."""

    provider = "file"

    def __init__(self, directory: str) -> None:
        self.directory = Path(directory)

    def send(self, to: str, subject: str, body: str) -> str:
        message_id = uuid.uuid4().hex
        message = EmailMessage()
        message["To"] = to
        message["From"] = "no-reply@localhost"
        message["Subject"] = subject
        message["Message-ID"] = f"<{message_id}@localhost>"
        # These files are read by developers, so keep the body as plain text. The default
        # quoted-printable encoding turns "=" into "=3D" and wraps long lines, which breaks
        # links copied straight from the file.
        message.set_content(body, cte="8bit")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / f"{message_id}.eml").write_bytes(bytes(message))
        except OSError as exc:
            raise EmailSendError("file_write_failed") from exc
        logger.info("development email written", extra={"provider": self.provider, "message_id": message_id})
        return message_id


def get_email_sender(settings: Settings) -> EmailSender:
    if settings.email_backend == "file":
        return FileEmailSender(settings.dev_mail_dir)
    # The SES adapter is added at deployment time, when AWS credentials are available.
    raise NotImplementedError("EMAIL_BACKEND=ses is not implemented yet")
