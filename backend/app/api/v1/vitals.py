"""Vital sign readings (api_contract_spec.md Section 6.10)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbDep
from app.schemas.vitals import VitalReadingCreate, VitalReadingList, VitalReadingResponse
from app.services.vitals_service import VitalsService

router = APIRouter(prefix="/vitals", tags=["vitals"])


def _service(session: DbDep) -> VitalsService:
    return VitalsService(session)


ServiceDep = Annotated[VitalsService, Depends(_service)]


@router.get("")
def list_readings(user: CurrentUser, service: ServiceDep) -> VitalReadingList:
    """Newest first."""
    return VitalReadingList(items=[VitalReadingResponse.model_validate(r) for r in service.readings(user.id)])


@router.post("", status_code=status.HTTP_201_CREATED)
def add_reading(body: VitalReadingCreate, user: CurrentUser, service: ServiceDep) -> VitalReadingResponse:
    reading = service.add(
        user.id, body.measured_on, body.measured_time, body.systolic, body.diastolic, body.heart_rate, body.context
    )
    return VitalReadingResponse.model_validate(reading)


@router.delete("/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_reading(reading_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> None:
    service.remove(user.id, reading_id)
