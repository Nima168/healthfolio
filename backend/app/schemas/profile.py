"""Health profile schemas (api_contract_spec.md Section 6.9)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ConditionStatus = Literal["active", "resolved", "unknown"]
PersonalField = Literal["date_of_birth", "sex", "blood_group", "height", "weight"]
AllergyCategory = Literal["drug", "food", "environmental", "other"]
RecordKind = Literal["surgery", "hospitalization", "family"]


class ProfileValueResponse(BaseModel):
    value: str
    unit: str | None
    updated_at: datetime


class AllergyResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: AllergyCategory | None
    reaction: str | None
    added_at: datetime


class RecordItemResponse(BaseModel):
    id: uuid.UUID
    kind: RecordKind
    name: str
    occurred_on: date | None
    relation: str | None
    notes: str | None


class DocumentStayResponse(BaseModel):
    """A hospital stay read from a discharge summary, as written."""

    source_document_id: uuid.UUID
    source_document_title: str | None
    facility_name: str | None
    admitted_on: date | None
    discharged_on: date | None
    diagnoses: list[str]


class ActiveMedicationResponse(BaseModel):
    id: uuid.UUID
    name: str
    strength: str | None
    dosage_text: str | None
    kind: Literal["prescription", "over_the_counter", "supplement"]


class ConditionResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: ConditionStatus
    origin: Literal["user_entered", "suggestion_accepted"]
    source_document_id: uuid.UUID | None
    source_document_title: str | None  # for an accepted suggestion; null when deleted


class ConditionSuggestionResponse(BaseModel):
    id: uuid.UUID
    name: str  # exactly as written in the document
    source_document_id: uuid.UUID
    source_document_title: str | None
    source_document_date: date | None


class LatestVitalResponse(BaseModel):
    value: str  # "128/84" or "72"
    unit: str
    measured_on: date
    measured_time: str | None  # HH:MM


class ProfileResponse(BaseModel):
    values: dict[PersonalField, ProfileValueResponse | None]
    bmi: float | None  # calculated from height and weight
    # Adult category for the BMI; null without a BMI or for an age under 18.
    bmi_category: Literal["underweight", "healthy", "overweight", "obesity_1", "obesity_2", "obesity_3"] | None
    allergies: list[AllergyResponse]
    conditions: list[ConditionResponse]
    suggestions: list[ConditionSuggestionResponse]
    surgeries: list[RecordItemResponse]
    hospitalizations: list[RecordItemResponse]  # entered by the user
    document_stays: list[DocumentStayResponse]  # read from discharge summaries
    family_history: list[RecordItemResponse]
    active_medications: list[ActiveMedicationResponse]  # marked as taking on the Medications page
    # The latest dated readings (from vital_readings), each with its own date.
    latest_blood_pressure: LatestVitalResponse | None
    latest_heart_rate: LatestVitalResponse | None


class ProfileHistoryEntry(BaseModel):
    field: str
    change: Literal["added", "changed", "removed"]
    previous_value: str | None
    new_value: str | None
    changed_at: datetime


class ProfileHistoryResponse(BaseModel):
    items: list[ProfileHistoryEntry]


def _name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Enter a name.")
    return cleaned


class ValuesUpdate(BaseModel):
    """Only the fields sent change; an empty string or null clears one."""

    model_config = ConfigDict(extra="forbid")

    date_of_birth: str | None = Field(default=None, max_length=20)
    sex: str | None = Field(default=None, max_length=30)
    blood_group: str | None = Field(default=None, max_length=5)
    height: str | None = Field(default=None, max_length=10)
    weight: str | None = Field(default=None, max_length=10)


class AllergyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    category: AllergyCategory | None = None
    reaction: str | None = Field(default=None, max_length=300)


class RecordItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RecordKind
    name: str = Field(min_length=1, max_length=300)
    occurred_on: date | None = None  # surgeries and hospitalizations
    relation: str | None = Field(default=None, max_length=50)  # family history
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str | None:
        return _name(value)

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        return " ".join(value.split()) or None if value else None


class ConditionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    status: ConditionStatus = "active"

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str | None:
        return _name(value)


class ConditionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=300)
    status: ConditionStatus | None = None

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        return _name(value)


class SuggestionReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "correct", "reject"]
    name: str | None = Field(default=None, max_length=300)  # the corrected name, for "correct"
    status: ConditionStatus = "unknown"  # a document never says whether it is still active

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        return _name(value)
