"""Runs against the real PostgreSQL test database (start it with `docker compose up -d`)."""

import pytest

from app.db.session import database_is_available, get_engine

pytestmark = pytest.mark.integration


def test_readiness_against_real_database(client):
    get_engine.cache_clear()

    assert database_is_available() is True
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "ok"
