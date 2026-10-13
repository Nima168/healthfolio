"""AI summaries of the whole history and of one document (api_contract_spec.md Section 6.12)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.ai.extractor import ChatClient, make_client
from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.core.errors import ApiError
from app.core.rate_limit import check_user_rate_limit
from app.models.document import Document
from app.models.summary import AiSummary
from app.schemas.summaries import SummaryState, SummaryView
from app.services.summary_facts import Facts
from app.services.summary_service import SummaryService, is_stale

router = APIRouter(tags=["summaries"])


def provide_ai_client(settings: SettingsDep) -> ChatClient | None:
    """The AI client, or None when no key is configured (replaced by a fake in tests)."""
    return make_client(settings) if settings.groq_api_key is not None else None


def _service(session: DbDep, settings: SettingsDep, client: Annotated[ChatClient | None, Depends(provide_ai_client)]):
    return SummaryService(session, settings, client)


ServiceDep = Annotated[SummaryService, Depends(_service)]


def _document(session: DbDep, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = session.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user_id, Document.deleted_at.is_(None))
    )
    if document is None:
        raise ApiError(404)
    return document


def _view(summary: AiSummary) -> SummaryView:
    return SummaryView(
        id=summary.id,
        scope=summary.scope,
        created_at=summary.created_at,
        model_version=summary.model_version,
        sections=summary.content["sections"],
        explanations=summary.general_knowledge_sections,
        insights=summary.insights,
        sources=summary.source_refs,
        dropped_count=summary.dropped_count,
    )


def _state(service: SummaryService, summary: AiSummary | None, facts: Facts, can_create: bool) -> SummaryState:
    return SummaryState(
        enabled=service.enabled,
        can_create=can_create,
        summary=_view(summary) if summary else None,
        stale=bool(summary and is_stale(summary, facts)),
    )


@router.get("/summaries/history")
def history_summary(user: CurrentUser, service: ServiceDep) -> SummaryState:
    facts = service.current_facts(user.id)
    return _state(service, service.latest(user.id), facts, bool(facts.records))


@router.post("/summaries/history", status_code=201)
def create_history_summary(user: CurrentUser, service: ServiceDep, settings: SettingsDep) -> SummaryState:
    check_user_rate_limit("summary", user.id, settings.summary_rate_limit_per_hour, 3600)
    summary = service.create(user.id)
    return _state(service, summary, service.current_facts(user.id), True)


@router.get("/documents/{document_id}/summary")
def document_summary(document_id: uuid.UUID, user: CurrentUser, session: DbDep, service: ServiceDep) -> SummaryState:
    document = _document(session, user.id, document_id)
    facts = service.current_facts(user.id, document)
    readable = service.readable(document) and bool(facts.records)
    return _state(service, service.latest(user.id, document.id), facts, readable)


@router.post("/documents/{document_id}/summary", status_code=201)
def create_document_summary(
    document_id: uuid.UUID, user: CurrentUser, session: DbDep, service: ServiceDep, settings: SettingsDep
) -> SummaryState:
    document = _document(session, user.id, document_id)
    check_user_rate_limit("summary", user.id, settings.summary_rate_limit_per_hour, 3600)
    summary = service.create(user.id, document)
    return _state(service, summary, service.current_facts(user.id, document), True)
