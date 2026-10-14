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
        app_env="production", cors_origins="https://healthfolio.onrender.com", email_backend="disabled"
    )
    with pytest.raises(EmailSendError):
        get_email_sender(production).send("a@example.com", "subject", "body")


def test_file_email_is_still_refused_in_production():
    with pytest.raises(ValueError, match="EMAIL_BACKEND=file"):
        settings(app_env="production", cors_origins="https://healthfolio.onrender.com")
