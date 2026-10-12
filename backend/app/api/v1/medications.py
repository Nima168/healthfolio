"""Medication records (api_contract_spec.md Section 6.6)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbDep
from app.schemas.medications import (
    MedicationCreate,
    MedicationHistoryResponse,
    MedicationListResponse,
    MedicationResponse,
    MedicationUpdate,
)
from app.services.medication_service import MedicationService

router = APIRouter(prefix="/medications", tags=["medications"])


def _service(session: DbDep) -> MedicationService:
    return MedicationService(session)


ServiceDep = Annotated[MedicationService, Depends(_service)]


@router.get("")
def list_medications(user: CurrentUser, service: ServiceDep) -> MedicationListResponse:
    return service.list(user.id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_medication(body: MedicationCreate, user: CurrentUser, service: ServiceDep) -> MedicationResponse:
    return service.create(user.id, body)


@router.patch("/{medication_id}")
def update_medication(
    medication_id: uuid.UUID, body: MedicationUpdate, user: CurrentUser, service: ServiceDep
) -> MedicationResponse:
    return service.update(user.id, medication_id, body)


@router.delete("/{medication_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medication(medication_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> None:
    service.delete(user.id, medication_id)


@router.get("/{medication_id}/history")
def medication_history(medication_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> MedicationHistoryResponse:
    return service.history(user.id, medication_id)
