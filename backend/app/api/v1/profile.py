"""Health profile (api_contract_spec.md Section 6.9)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbDep
from app.models.document import Document
from app.models.prescription import Condition
from app.schemas.profile import (
    ActiveMedicationResponse,
    AllergyCreate,
    AllergyResponse,
    ConditionCreate,
    ConditionResponse,
    ConditionSuggestionResponse,
    ConditionUpdate,
    DocumentStayResponse,
    LatestVitalResponse,
    ProfileHistoryEntry,
    ProfileHistoryResponse,
    ProfileResponse,
    ProfileValueResponse,
    RecordItemCreate,
    RecordItemResponse,
    SuggestionReview,
    ValuesUpdate,
)
from app.services.profile_service import SINGLE_FIELDS, ProfileService, clean_value
from app.services.vitals_service import VitalsService

router = APIRouter(prefix="/profile", tags=["profile"])


def _service(session: DbDep) -> ProfileService:
    return ProfileService(session)


ServiceDep = Annotated[ProfileService, Depends(_service)]


def _condition(service: ProfileService, condition: Condition) -> ConditionResponse:
    document = service.session.get(Document, condition.source_document_id) if condition.source_document_id else None
    return ConditionResponse(
        id=condition.id,
        name=condition.name,
        status=condition.status,
        origin=condition.origin,
        source_document_id=condition.source_document_id,
        source_document_title=document.title if document and document.deleted_at is None else None,
    )


def _allergy(value) -> AllergyResponse:
    return AllergyResponse(
        id=value.id, name=value.value, category=value.category, reaction=value.detail, added_at=value.created_at
    )


def _record(item) -> RecordItemResponse:
    return RecordItemResponse(
        id=item.id,
        kind=item.kind,
        name=item.name,
        occurred_on=item.occurred_on,
        relation=item.relation,
        notes=item.notes,
    )


def latest_vital(reading, kind: str) -> LatestVitalResponse | None:
    if reading is None:
        return None
    value, unit = (
        (f"{reading.systolic}/{reading.diastolic}", "mmHg")
        if kind == "blood_pressure"
        else (str(reading.heart_rate), "bpm")
    )
    return LatestVitalResponse(
        value=value,
        unit=unit,
        measured_on=reading.measured_on,
        measured_time=reading.measured_time.strftime("%H:%M") if reading.measured_time else None,
    )


def _profile(service: ProfileService, user_id: uuid.UUID) -> ProfileResponse:
    data = service.profile(user_id)
    latest = VitalsService(service.session).latest(user_id)
    values = {}
    for field in SINGLE_FIELDS:
        value = data["values"].get(field)
        values[field] = (
            ProfileValueResponse(value=value.value, unit=value.unit, updated_at=value.updated_at) if value else None
        )
    return ProfileResponse(
        values=values,
        bmi=data["bmi"],
        bmi_category=data["bmi_category"],
        latest_blood_pressure=latest_vital(latest["blood_pressure"], "blood_pressure"),
        latest_heart_rate=latest_vital(latest["heart_rate"], "heart_rate"),
        allergies=[_allergy(a) for a in data["allergies"]],
        surgeries=[_record(r) for r in data["surgeries"]],
        hospitalizations=[_record(r) for r in data["hospitalizations"]],
        document_stays=[
            DocumentStayResponse(
                source_document_id=stay["document"].id,
                source_document_title=stay["document"].title,
                facility_name=stay["facility_name"],
                admitted_on=stay["admitted_on"],
                discharged_on=stay["discharged_on"],
                diagnoses=stay["diagnoses"],
            )
            for stay in data["document_stays"]
        ],
        family_history=[_record(r) for r in data["family_history"]],
        active_medications=[
            ActiveMedicationResponse(id=m.id, name=m.name, strength=m.strength, dosage_text=m.dosage_text, kind=m.kind)
            for m in data["active_medications"]
        ],
        conditions=[_condition(service, c) for c in data["conditions"]],
        suggestions=[
            ConditionSuggestionResponse(
                id=condition.id,
                name=condition.name,
                source_document_id=document.id,
                source_document_title=document.title,
                source_document_date=document.document_date,
            )
            for condition, document in data["suggestions"]
        ],
    )


@router.get("")
def get_profile(user: CurrentUser, service: ServiceDep) -> ProfileResponse:
    return _profile(service, user.id)


@router.patch("/values")
def update_values(body: ValuesUpdate, user: CurrentUser, service: ServiceDep) -> ProfileResponse:
    """Every field sent is validated first, so a mistake in one changes nothing."""
    sent = {field: getattr(body, field) for field in body.model_fields_set}
    for field, raw in sent.items():
        if raw is not None and raw.strip():
            clean_value(field, raw)
    for field, raw in sent.items():
        service.set_value(user.id, field, raw)
    return _profile(service, user.id)


@router.get("/history")
def profile_history(user: CurrentUser, service: ServiceDep) -> ProfileHistoryResponse:
    return ProfileHistoryResponse(
        items=[
            ProfileHistoryEntry(
                field=entry.field,
                change=entry.change_origin,
                previous_value=entry.previous_value,
                new_value=entry.new_value,
                changed_at=entry.changed_at,
            )
            for entry in service.history(user.id)
        ]
    )


@router.post("/allergies", status_code=status.HTTP_201_CREATED)
def add_allergy(body: AllergyCreate, user: CurrentUser, service: ServiceDep) -> AllergyResponse:
    return _allergy(service.add_allergy(user.id, body.name, body.category, body.reaction))


@router.delete("/allergies/{allergy_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_allergy(allergy_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> None:
    service.remove_allergy(user.id, allergy_id)


@router.post("/records", status_code=status.HTTP_201_CREATED)
def add_record(body: RecordItemCreate, user: CurrentUser, service: ServiceDep) -> RecordItemResponse:
    """A past surgery, a hospitalization, or a condition in the family."""
    return _record(service.add_record(user.id, body.kind, body.name, body.occurred_on, body.relation, body.notes))


@router.delete("/records/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_record(item_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> None:
    service.remove_record(user.id, item_id)


@router.post("/conditions", status_code=status.HTTP_201_CREATED)
def add_condition(body: ConditionCreate, user: CurrentUser, service: ServiceDep) -> ConditionResponse:
    condition = service.add_condition(user.id, body.name, body.status)
    service.session.commit()
    return _condition(service, condition)


@router.patch("/conditions/{condition_id}")
def update_condition(
    condition_id: uuid.UUID, body: ConditionUpdate, user: CurrentUser, service: ServiceDep
) -> ConditionResponse:
    return _condition(service, service.update_condition(user.id, condition_id, body.name, body.status))


@router.delete("/conditions/{condition_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_condition(condition_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> None:
    service.remove_condition(user.id, condition_id)


@router.post("/suggestions/{suggestion_id}")
def review_suggestion(
    suggestion_id: uuid.UUID, body: SuggestionReview, user: CurrentUser, service: ServiceDep
) -> ProfileResponse:
    """Accept, correct, or reject a diagnosis suggested from a document."""
    service.review_suggestion(user.id, suggestion_id, body.action, body.name, body.status)
    return _profile(service, user.id)
