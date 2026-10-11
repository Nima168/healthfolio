"""Liveness and readiness checks (observability_and_reliability_spec.md Section 6)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.errors import ApiError
from app.db.session import database_is_available

router = APIRouter(prefix="/health", tags=["health"])


def database_status() -> bool:
    """Dependency wrapper so tests can simulate an unavailable database."""
    return database_is_available()


@router.get("/live")
def live() -> dict[str, str]:
    """The process is running. Does not check dependencies."""
    return {"status": "alive"}


@router.get("/ready")
def ready(database_ok: Annotated[bool, Depends(database_status)]) -> dict[str, object]:
    """The application can serve requests: essential dependencies are reachable."""
    if not database_ok:
        raise ApiError(503, details=[{"field": "database", "issue": "unavailable"}])
    return {"status": "ready", "checks": {"database": "ok"}}
