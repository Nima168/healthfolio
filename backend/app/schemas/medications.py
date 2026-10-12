"""Medication record schemas (api_contract_spec.md Section 6.6)."""

import uuid
from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MedicationStatus = Literal["active", "stopped", "unknown"]
MedicationChange = Literal["added", "edited", "status_changed", "removed"]


class MedicationResponse(BaseModel):
    id: uuid.UUID
    name: str
    strength: str | None
    dosage_text: str | None  # how and when to take it, as written or entered
    duration_text: str | None
    prescriber_name: str | None
    start_date: date | None
    end_date: date | None
    notes: str | None
    status: MedicationStatus
    origin: Literal["user_entered", "document_extracted", "suggestion_accepted"]
    status_confirmed: bool  # the user marked it as taking or stopped
    edited: bool  # the user changed it after it was read from a document
    review_reason: str | None  # unclear in the document; cleared once the user edits it
    source_document_id: uuid.UUID | None
    source_document_title: str | None  # null when there is no source or it was deleted
    source_document_date: date | None
    source_document_deleted: bool
    updated_at: datetime


class MedicationListResponse(BaseModel):
    items: list[MedicationResponse]


class MedicationHistoryEntry(BaseModel):
    id: uuid.UUID
    change: MedicationChange
    changed_at: datetime
    changes: dict[str, list[Any]]  # field: [before, after]
    snapshot: dict[str, Any]  # all values before the change


class MedicationHistoryResponse(BaseModel):
    items: list[MedicationHistoryEntry]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class _Fields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strength: str | None = Field(default=None, max_length=100)
    dosage_text: str | None = Field(default=None, max_length=300)
    duration_text: str | None = Field(default=None, max_length=100)
    prescriber_name: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("strength", "dosage_text", "duration_text", "prescriber_name", "notes")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return _clean(value)

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date cannot be before the start date.")
        return self


class MedicationCreate(_Fields):
    name: str = Field(min_length=1, max_length=200)
    status: MedicationStatus = "active"

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = _clean(value)
        if not cleaned:
            raise ValueError("Enter the medicine name.")
        return cleaned


class MedicationUpdate(_Fields):
    """Only the fields sent are changed; send null to clear an optional field."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: MedicationStatus | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _clean(value)
        if not cleaned:
            raise ValueError("Enter the medicine name.")
        return cleaned
