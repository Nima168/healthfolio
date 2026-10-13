"""Record search (api_contract_spec.md Section 9.1). POST, so the query never appears in logged URLs."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbDep
from app.core.errors import ApiError
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.services.search_service import SearchCriteria, SearchService

router = APIRouter(prefix="/search", tags=["search"])


def _service(session: DbDep) -> SearchService:
    return SearchService(session)


ServiceDep = Annotated[SearchService, Depends(_service)]


def _invalid(field: str, issue: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", issue, [{"field": field, "issue": issue}])


@router.post("")
def search(body: SearchRequest, user: CurrentUser, service: ServiceDep) -> SearchResponse:
    criteria = SearchCriteria(
        query=body.query,
        document_type=body.document_type,
        date_from=body.date_from,
        date_to=body.date_to,
        condition=body.condition,
        provider=body.provider,
    )
    if not any(vars(criteria).values()):
        raise _invalid("query", "Enter something to search for, or choose a filter.")
    if body.date_from and body.date_to and body.date_to < body.date_from:
        raise _invalid("date_to", "The end date cannot be before the start date.")
    if body.cursor is not None and not body.cursor.isdigit():
        raise _invalid("cursor", "The cursor is not valid.")

    found = service.search(user.id, criteria)
    start = int(body.cursor or 0)
    page = found[start : start + body.limit]
    return SearchResponse(
        items=[
            SearchResult(
                record_type=r.record_type,
                id=r.id,
                title=r.title,
                date=r.date,
                matched_field=r.matched_field,
                snippet=r.snippet,
                source_document_id=r.source_document.id if r.source_document else None,
                source_document_title=r.source_document.title if r.source_document else None,
                link=r.link,
            )
            for r in page
        ],
        total=len(found),
        next_cursor=str(start + body.limit) if start + body.limit < len(found) else None,
    )
