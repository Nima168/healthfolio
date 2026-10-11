import pytest
from fastapi.testclient import TestClient

from app.core.errors import ApiError


@pytest.fixture
def client_with_test_routes(app):
    @app.get("/api/v1/_test/validation")
    def needs_int(limit: int):
        return {"limit": limit}

    @app.get("/api/v1/_test/crash")
    def crash():
        raise RuntimeError("boom password=hunter2 postgresql://u:secretpw@db:5432/x")

    @app.get("/api/v1/_test/conflict")
    def conflict():
        raise ApiError(409)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def assert_standard_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
    return body["error"]


def test_unknown_route_returns_standard_404(client):
    assert_standard_error(client.get("/api/v1/does-not-exist"), 404, "NOT_FOUND")


def test_validation_error_lists_field_without_echoing_value(client_with_test_routes):
    response = client_with_test_routes.get("/api/v1/_test/validation?limit=not-a-number")

    error = assert_standard_error(response, 422, "VALIDATION_ERROR")
    assert error["details"][0]["field"] == "limit"
    assert "not-a-number" not in response.text


def test_api_error_uses_default_code_and_message(client_with_test_routes):
    error = assert_standard_error(client_with_test_routes.get("/api/v1/_test/conflict"), 409, "CONFLICT")
    assert error["message"]


def test_unexpected_error_hides_internal_details(client_with_test_routes):
    response = client_with_test_routes.get("/api/v1/_test/crash")

    assert_standard_error(response, 500, "INTERNAL_ERROR")
    for leak in ("boom", "hunter2", "secretpw", "Traceback", "RuntimeError"):
        assert leak not in response.text
