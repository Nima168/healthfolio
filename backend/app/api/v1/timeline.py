"""Health timeline (api_contract_spec.md Section 6.7)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbDep
from app.core.errors import ApiError
from app.schemas.timeline import TimelineCategory, TimelineEntryResponse, TimelinePage
from app.services.timeline_service import TimelineService

router = APIRouter(prefix="/timeline", tags=["timeline"])


def _service(session: DbDep) -> TimelineService:
    return TimelineService(session)


ServiceDep = Annotated[TimelineService, Depends(_service)]


def _offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isdigit():
        raise ApiError(422, "VALIDATION_ERROR", "The cursor is not valid.", [{"field": "cursor", "issue": "Invalid."}])
    return int(cursor)


@router.get("")
def timeline(
    user: CurrentUser,
    service: ServiceDep,
    category: Annotated[list[TimelineCategory] | None, Query()] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=12)] = None,
) -> TimelinePage:
    """Newest first, undated last. `category` may repeat; dates leave out undated entries."""
    if date_from and date_to and date_to < date_from:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "The end date cannot be before the start date.",
            [{"field": "date_to", "issue": "The end date cannot be before the start date."}],
        )
    start = _offset(cursor)
    entries = service.entries(user.id, set(category or []), date_from, date_to)
    page = entries[start : start + limit]
    more = start + limit < len(entries)
    return TimelinePage(
        items=[TimelineEntryResponse.model_validate(entry) for entry in page],
        next_cursor=str(start + limit) if more else None,
    )
