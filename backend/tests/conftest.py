import os
import shutil
import tempfile
from pathlib import Path

# Test settings must be in place before the app (and its settings) are imported.
# Environment variables take precedence over backend/.env.
os.environ["APP_ENV"] = "test"
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://healthcare:healthcare_dev_password@localhost:5432/healthcare_test",
)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["EMAIL_BACKEND"] = "file"
os.environ["DEV_MAIL_DIR"] = tempfile.mkdtemp(prefix="test_mail_")
os.environ["DOCUMENT_STORAGE_DIR"] = tempfile.mkdtemp(prefix="test_documents_")
os.environ["EXTRACTION_ENABLED"] = "false"  # tests turn it on explicitly where needed

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.api.v1.health import database_status  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.db.session import get_engine, get_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALL_TABLES = (
    "follow_ups, suggestions, conditions, medications, observations, processing_jobs, documents, "
    "audit_events, email_deliveries, password_reset_tokens, refresh_tokens, users"
)


@pytest.fixture(autouse=True)
def reset_rate_limits():
    limiter.reset()


@pytest.fixture
def app():
    get_settings.cache_clear()
    application = create_app()
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    # https base URL so the Secure refresh cookie is sent back, as a browser would on HTTPS.
    # raise_server_exceptions=False lets us assert on 500 response bodies.
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def database_up(app):
    app.dependency_overrides[database_status] = lambda: True


@pytest.fixture
def database_down(app):
    app.dependency_overrides[database_status] = lambda: False


# ---------- real database (integration) ----------


@pytest.fixture(scope="session")
def migrated_database():
    """Bring the test database to the latest migration once per test run."""
    get_settings.cache_clear()
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest.fixture
def db(migrated_database):
    """Empty all tables before each test; yields a session for direct checks."""
    with get_engine().begin() as connection:
        connection.execute(text(f"TRUNCATE {ALL_TABLES} CASCADE"))
    session = get_session_factory()()
    yield session
    session.close()


@pytest.fixture
def mail_dir():
    directory = Path(os.environ["DEV_MAIL_DIR"])
    for message in directory.glob("*.eml"):
        message.unlink()
    return directory


@pytest.fixture
def storage_dir():
    """The temporary document storage folder, emptied before each test."""
    directory = Path(os.environ["DOCUMENT_STORAGE_DIR"])
    for child in directory.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    return directory
