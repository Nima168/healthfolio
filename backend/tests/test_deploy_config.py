"""Settings for a hosted deployment: provider database URLs and running without an email service."""

import pytest

from app.core.config import Settings
from app.services.email import EmailSendError, get_email_sender

SECRET = "x" * 40


def settings(**overrides) -> Settings:
    values = {"database_url": "postgresql+psycopg://u:p@h/db", "jwt_secret": SECRET} | overrides
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("url", ["postgres://u:p@h:5432/db", "postgresql://u:p@h:5432/db"])
def test_provider_database_urls_use_the_psycopg_driver(url):
    assert settings(database_url=url).database_url.get_secret_value() == "postgresql+psycopg://u:p@h:5432/db"


def test_production_may_run_without_email_and_sends_nothing():
    production = settings(
        app_env="production", cors_origins="https://healthfolio.example.org", email_backend="disabled"
    )
    with pytest.raises(EmailSendError):
        get_email_sender(production).send("a@example.com", "subject", "body")


def test_file_email_is_still_refused_in_production():
    with pytest.raises(ValueError, match="EMAIL_BACKEND=file"):
        settings(app_env="production", cors_origins="https://healthfolio.example.org")


# ---------- S3 document storage (fake client, no AWS) ----------

KEY = "11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222"


class FakeBody:
    def __init__(self, data: bytes) -> None:
        self.data, self.closed = data, False

    def iter_chunks(self, size: int):
        for start in range(0, len(self.data), size):
            yield self.data[start : start + size]

    def close(self) -> None:
        self.closed = True


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.extra: dict[str, dict] = {}

    def upload_fileobj(self, handle, bucket, key, ExtraArgs=None):  # noqa: N803 (boto3's name)
        self.objects[f"{bucket}/{key}"] = handle.read()
        self.extra[key] = ExtraArgs or {}

    def get_object(self, Bucket, Key):  # noqa: N803
        if f"{Bucket}/{Key}" not in self.objects:
            raise KeyError(Key)
        return {"Body": FakeBody(self.objects[f"{Bucket}/{Key}"])}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop(f"{Bucket}/{Key}", None)


def test_s3_storage_saves_reads_and_deletes_encrypted_documents():
    from app.services.storage import S3DocumentStorage

    fake = FakeS3()
    storage = S3DocumentStorage("docs", client=fake)
    storage.save(KEY, [b"%PDF-", b"x" * 100_000])

    assert fake.extra[KEY] == {"ServerSideEncryption": "AES256"}
    assert b"".join(storage.open(KEY)) == b"%PDF-" + b"x" * 100_000
    storage.delete(KEY)
    assert fake.objects == {}


def test_s3_storage_errors_and_bad_keys():
    from app.services.storage import S3DocumentStorage, StorageError

    storage = S3DocumentStorage("docs", client=FakeS3())
    with pytest.raises(StorageError):
        storage.open(KEY)
    with pytest.raises(ValueError):
        storage.save("../etc/passwd", [b"x"])


def test_s3_needs_a_bucket_in_production():
    with pytest.raises(ValueError, match="S3_BUCKET"):
        settings(
            app_env="production",
            cors_origins="https://example.org",
            email_backend="disabled",
            storage_backend="s3",
        )


# ---------- Amazon SES email (fake client, no AWS) ----------


class FakeSes:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[dict] = []
        self.error = error

    def send_email(self, **request):
        if self.error:
            raise self.error
        self.sent.append(request)
        return {"MessageId": "msg-1"}


def test_ses_sends_plain_text_from_the_verified_sender():
    from app.services.email import SesEmailSender

    fake = FakeSes()
    message_id = SesEmailSender("Healthfolio <sender@example.com>", client=fake).send(
        "user@example.com", "Reset your password", "Open this link"
    )

    assert message_id == "msg-1"
    [request] = fake.sent
    assert request["FromEmailAddress"] == "Healthfolio <sender@example.com>"
    assert request["Destination"] == {"ToAddresses": ["user@example.com"]}
    assert request["Content"]["Simple"]["Body"]["Text"]["Data"] == "Open this link"


def test_ses_failures_are_recorded_without_the_provider_message():
    from app.services.email import SesEmailSender

    sender = SesEmailSender("sender@example.com", client=FakeSes(RuntimeError("user@example.com not verified")))
    with pytest.raises(EmailSendError) as failure:
        sender.send("user@example.com", "s", "b")
    assert str(failure.value) == "ses_RuntimeError"


def test_ses_needs_a_sender():
    with pytest.raises(ValueError, match="EMAIL_FROM"):
        settings(email_backend="ses")
