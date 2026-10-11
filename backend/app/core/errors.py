"""Standard error responses (api_contract_spec.md Section 8).

Every error leaves the API as:
    {"error": {"code": ..., "message": ..., "details": [...], "request_id": ...}}

Messages are generic per status code so internal details, stack traces, and
submitted values never reach the client.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)

# status code -> (machine-readable code, user-safe message)
_STATUS_ERRORS: dict[int, tuple[str, str]] = {
    400: ("BAD_REQUEST", "The request could not be processed."),
    401: ("UNAUTHENTICATED", "Authentication is required."),
    403: ("FORBIDDEN", "You do not have permission to perform this action."),
    404: ("NOT_FOUND", "The requested resource was not found."),
    405: ("METHOD_NOT_ALLOWED", "This method is not allowed for the requested resource."),
    409: ("CONFLICT", "The request conflicts with the current state of the resource."),
    413: ("CONTENT_TOO_LARGE", "The uploaded content exceeds the allowed size."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "The content type is not supported."),
    422: ("VALIDATION_ERROR", "The request contains invalid fields."),
    429: ("RATE_LIMITED", "Too many requests. Please try again later."),
    500: ("INTERNAL_ERROR", "An unexpected error occurred."),
    503: ("SERVICE_UNAVAILABLE", "The service is temporarily unavailable."),
}


class ApiError(Exception):
    """Raise from application code to return a standard error response."""

    def __init__(
        self,
        status_code: int,
        code: str | None = None,
        message: str | None = None,
        details: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        default_code, default_message = _STATUS_ERRORS.get(status_code, _STATUS_ERRORS[500])
        self.status_code = status_code
        self.code = code or default_code
        self.message = message or default_message
        self.details = details or []
        self.headers = headers
        super().__init__(self.code)


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = request_id_var.get()
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": request_id,
        }
    }
    response_headers = {"X-Request-ID": request_id, **(headers or {})}
    return JSONResponse(status_code=status_code, content=body, headers=response_headers)


async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details, headers=exc.headers)


async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = _STATUS_ERRORS.get(exc.status_code, ("HTTP_ERROR", "The request could not be processed."))
    return error_response(exc.status_code, code, message, headers=getattr(exc, "headers", None))


async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for error in exc.errors():
        # Drop the "body"/"query"/"path" prefix; never echo the submitted value.
        location = [str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path", "header")]
        issue = str(error.get("msg", "Invalid value.")).removeprefix("Value error, ")
        details.append({"field": ".".join(location) or "request", "issue": issue})
    code, message = _STATUS_ERRORS[422]
    return error_response(422, code, message, details)


async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled exception", exc_info=exc)
    code, message = _STATUS_ERRORS[500]
    return error_response(500, code, message)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
