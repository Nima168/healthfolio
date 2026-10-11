import os

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

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.health import database_status  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def app():
    get_settings.cache_clear()
    application = create_app()
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    # raise_server_exceptions=False lets us assert on the 500 response body.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def database_up(app):
    app.dependency_overrides[database_status] = lambda: True


@pytest.fixture
def database_down(app):
    app.dependency_overrides[database_status] = lambda: False
