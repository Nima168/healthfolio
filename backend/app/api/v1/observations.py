"""Extracted results and adding follow-ups from a document (api_contract_spec.md Sections 6.2, 6.3)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.schemas.observations import DocumentExtractionResponse
from app.services.observation_service import ObservationService

router = APIRouter(tags=["observations"])


def _service(session: DbDep, settings: SettingsDep) -> ObservationService:
    return ObservationService(session, settings)


ServiceDep = Annotated[ObservationService, Depends(_service)]


@router.get("/documents/{document_id}/observations")
def document_observations(document_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> DocumentExtractionResponse:
    return service.for_document(user.id, document_id)


@router.post("/documents/{document_id}/extract", status_code=status.HTTP_202_ACCEPTED)
def request_extraction(document_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> DocumentExtractionResponse:
    return service.request_extraction(user.id, document_id)


@router.post("/documents/{document_id}/follow-ups", status_code=status.HTTP_201_CREATED)
def add_follow_ups(document_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> DocumentExtractionResponse:
    """Add as reminders: track this document's follow-ups (api_contract_spec.md Section 6.3)."""
    return service.add_follow_ups(user.id, document_id)
