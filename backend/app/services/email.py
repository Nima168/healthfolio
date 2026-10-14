"""Email delivery behind a replaceable interface (backend_spec.md Section 2.1).

Emails never contain medical information. Message bodies and links are never logged.
"""

import logging
import uuid
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Protocol

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


class DisabledEmailSender:
    """No email service configured (a demo deployment): every send fails and is recorded as such."""

    provider = "disabled"

    def send(self, to: str, subject: str, body: str) -> str:
        raise EmailSendError("email_disabled")


class SesEmailSender:
    """Amazon SES (v2 API). Credentials come from the server's IAM role, never from code."""

    provider = "ses"

    def __init__(self, sender: str, client: Any = None) -> None:
        self.sender = sender
        if client is None:
            import boto3  # only needed when SES is used

            client = boto3.client("sesv2")
        self.client = client

    def send(self, to: str, subject: str, body: str) -> str:
        try:
            response = self.client.send_email(
                FromEmailAddress=self.sender,
                Destination={"ToAddresses": [to]},
                Content={
                    "Simple": {
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                    }
                },
            )
        except Exception as exc:  # botocore raises several unrelated error types
            # Only the error class is recorded: SES messages can include the recipient address.
            raise EmailSendError(f"ses_{type(exc).__name__}"[:64]) from exc
        logger.info("email sent", extra={"provider": self.provider})
        return str(response["MessageId"])


def get_email_sender(settings: Settings) -> EmailSender:
    if settings.email_backend == "file":
        return FileEmailSender(settings.dev_mail_dir)
    if settings.email_backend == "disabled":
        return DisabledEmailSender()
    return SesEmailSender(settings.email_from or "")  # "ses"
