def test_generates_request_id_when_missing(client):
    first = client.get("/api/v1/health/live").headers["X-Request-ID"]
    second = client.get("/api/v1/health/live").headers["X-Request-ID"]

    assert first and second and first != second


def test_echoes_valid_incoming_request_id(client):
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "trace-abc_123"})

    assert response.headers["X-Request-ID"] == "trace-abc_123"


def test_replaces_unsafe_incoming_request_id(client):
    unsafe = "bad id\nwith newline" + "x" * 100
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": unsafe.replace("\n", " ")})

    assert response.headers["X-Request-ID"] != unsafe
    assert " " not in response.headers["X-Request-ID"]


def test_cors_allows_configured_origin_and_exposes_request_id(client):
    response = client.get("/api/v1/health/live", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


def test_cors_rejects_unknown_origin(client):
    response = client.get("/api/v1/health/live", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
