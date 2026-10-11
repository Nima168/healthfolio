import json
import logging

from app.core.logging import REDACTED, JsonFormatter, redact_text


def format_record(message, **extra):
    record = logging.LogRecord("test", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter("test").format(record))


def test_log_line_has_required_fields():
    entry = format_record("hello")

    for field in ("timestamp", "level", "component", "environment", "request_id", "event"):
        assert field in entry


def test_sensitive_extra_fields_are_redacted():
    entry = format_record("login", password="hunter2", access_token="abc.def", user_id="u1")

    assert entry["password"] == REDACTED
    assert entry["access_token"] == REDACTED
    assert entry["user_id"] == "u1"


def test_nested_sensitive_fields_are_redacted():
    entry = format_record("headers", headers={"Authorization": "Bearer xyz", "Accept": "json"})

    assert entry["headers"]["Authorization"] == REDACTED
    assert entry["headers"]["Accept"] == "json"


def test_secrets_in_message_text_are_redacted():
    text = redact_text("auth Bearer eyJhbGci.x.y and password=hunter2 via postgresql://u:pw@db:5432/x")

    for leak in ("eyJhbGci", "hunter2", ":pw@"):
        assert leak not in text


def test_access_log_omits_query_string(client, capsys):
    client.get("/api/v1/health/live?search=diabetes")

    output = capsys.readouterr().out
    access_lines = [json.loads(line) for line in output.splitlines() if '"request completed"' in line]
    assert access_lines, "expected an access log line"
    assert access_lines[-1]["path"] == "/api/v1/health/live"
    assert "diabetes" not in output
