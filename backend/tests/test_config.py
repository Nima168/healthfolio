import pytest
from pydantic import ValidationError

from app.core.config import Settings

DB_URL = "postgresql+psycopg://user:topsecret@localhost:5432/db"
JWT_SECRET = "jwt-secret-value-" + "y" * 32


def make(**values):
    # _env_file=None: ignore backend/.env so each test controls its own inputs.
    values.setdefault("jwt_secret", JWT_SECRET)
    return Settings(_env_file=None, **values)


def production(**values):
    return make(
        database_url=DB_URL,
        app_env="production",
        cors_origins="https://app.test",
        email_backend="ses",
        email_from="sender@app.test",
        **values,
    )


def test_missing_database_url_fails_clearly(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as excinfo:
        make()
    assert "database_url" in str(excinfo.value)


def test_database_url_is_never_shown(monkeypatch):
    settings = make(database_url=DB_URL)

    assert "topsecret" not in repr(settings)
    assert "topsecret" not in str(settings.model_dump())


def test_invalid_value_error_does_not_echo_secret_input():
    with pytest.raises(ValidationError) as excinfo:
        make(database_url=DB_URL, max_upload_mb="not-a-number")
    assert "topsecret" not in str(excinfo.value)


def test_cors_origins_parsed_from_comma_separated_string(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")

    assert make(database_url=DB_URL).cors_origins == ["http://a.test", "http://b.test"]


def test_spec_defaults():
    settings = make(database_url=DB_URL)

    assert (settings.max_upload_mb, settings.access_token_minutes, settings.refresh_token_days) == (20, 15, 7)


def test_production_rejects_debug_logging():
    with pytest.raises(ValidationError):
        production(log_level="DEBUG")


def test_production_requires_cors_origins(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    with pytest.raises(ValidationError):
        make(database_url=DB_URL, app_env="production", email_backend="ses")


def test_production_requires_secure_cookies():
    with pytest.raises(ValidationError):
        production(cookie_secure=False)


def test_production_rejects_file_email_backend():
    with pytest.raises(ValidationError):
        make(database_url=DB_URL, app_env="production", cors_origins="https://app.test", email_backend="file")


def test_jwt_secret_required_and_minimum_length(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=DB_URL)
    with pytest.raises(ValidationError) as excinfo:
        make(database_url=DB_URL, jwt_secret="too-short-secret")
    assert "too-short-secret" not in str(excinfo.value)


def test_production_disables_docs(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(production())
    with TestClient(app) as client:
        assert client.get("/api/v1/docs").status_code == 404
        assert client.get("/api/v1/openapi.json").status_code == 404
