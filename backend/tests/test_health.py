def test_live_returns_alive(client):
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_live_does_not_depend_on_database(client, database_down):
    assert client.get("/api/v1/health/live").status_code == 200


def test_ready_when_database_available(client, database_up):
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


def test_ready_returns_503_in_standard_format_when_database_down(client, database_down):
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "SERVICE_UNAVAILABLE"
    assert error["details"] == [{"field": "database", "issue": "unavailable"}]
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_ready_response_reveals_no_connection_details(client, database_down):
    body = client.get("/api/v1/health/ready").text.lower()

    for leak in ("postgresql", "localhost", "5432", "password", "healthcare_test"):
        assert leak not in body
