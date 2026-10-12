"""Structured JSON logging with redaction (observability_and_reliability_spec.md Section 4).

Every log line is one JSON object with timestamp, level, component, environment,
request ID, and event. Sensitive values are redacted before the line is written.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Set per request by the request-ID middleware; "-" outside a request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

REDACTED = "[REDACTED]"

# A field is redacted when its name contains any of these fragments.
_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "token",
    "authorization",
    "cookie",
    "secret",
    "api_key",
    "database_url",
    "email",
)

# Patterns redacted inside free-text messages and exception traces.
_SENSITIVE_PATTERNS = [
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), f"Bearer {REDACTED}"),
    (re.compile(r"(?i)\b(password|passwd|token|secret|api_key)\s*[=:]\s*[^\s,;&]+"), rf"\1={REDACTED}"),
    (re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@]+@[^\s]+"), REDACTED),  # URLs with credentials
]

# Standard LogRecord attributes; anything else on the record came from `extra=`.
_RESERVED_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


def redact_text(text: str) -> str:
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(key: str, value: Any) -> Any:
    if any(fragment in key.lower() for fragment in _SENSITIVE_KEY_FRAGMENTS):
        return REDACTED
    if isinstance(value, dict):
        return {k: redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, str):
        return redact_text(value)
    return value


class JsonFormatter(logging.Formatter):
    def __init__(self, environment: str) -> None:
        super().__init__()
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "environment": self.environment,
            "request_id": request_id_var.get(),
            "event": redact_text(record.getMessage()),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                entry[key] = redact_value(key, value)
        if record.exc_info:
            entry["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(entry, default=str)


class _StdoutHandler(logging.StreamHandler):
    """Writes to whatever sys.stdout is at emit time (not at setup time)."""

    @property
    def stream(self):  # type: ignore[override]
        return sys.stdout

    @stream.setter
    def stream(self, _value) -> None:
        pass


def configure_logging(level: str, environment: str) -> None:
    handler = _StdoutHandler()
    handler.setFormatter(JsonFormatter(environment))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Uvicorn's own access log would print full URLs (including query strings);
    # our middleware writes a sanitized access log instead.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    # HTTP client libraries log full URLs (with query strings) at INFO: httpx is used by the
    # Groq SDK and the test client; the others are listed in case a dependency brings them in.
    for name in ("httpx", "httpcore", "httpx2", "httpcore2"):
        logging.getLogger(name).setLevel(logging.WARNING)
