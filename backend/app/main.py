"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware, UploadSizeLimitMiddleware

API_PREFIX = "/api/v1"
MULTIPART_OVERHEAD_BYTES = 64 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.app_env.value)

    # Interactive docs are for development only (backend_spec.md Section 11.3).
    docs_enabled = not settings.is_production
    app = FastAPI(
        title="Healthcare Decision-Support API",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs_enabled else None,
    )

    # Middleware added last runs first: request ID wraps CORS so every response carries it,
    # and CORS wraps the upload limit so the browser can read a 413 response.
    app.add_middleware(
        UploadSizeLimitMiddleware,
        # The file limit plus a small allowance for the multipart envelope and form fields.
        max_body_bytes=settings.max_upload_mb * 1024 * 1024 + MULTIPART_OVERHEAD_BYTES,
        paths=(f"{API_PREFIX}/documents",),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # for the HttpOnly refresh-token cookie
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER, "X-CSRF-Protection"],
        expose_headers=[REQUEST_ID_HEADER, "Content-Disposition"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=API_PREFIX)
    return app


app = create_app()
