"""Vital sign reading schemas (api_contract_spec.md Section 6.10)."""

import uuid
from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VitalReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    measured_on: date
    measured_time: time | None
    systolic: int | None  # mmHg
    diastolic: int | None  # mmHg
    heart_rate: int | None  # beats per minute
    context: str | None


class VitalReadingList(BaseModel):
    items: list[VitalReadingResponse]


class VitalReadingCreate(BaseModel):
    """A blood pressure (both numbers), a heart rate, or both. Ranges are checked by the service."""

    model_config = ConfigDict(extra="forbid")

    measured_on: date
    measured_time: time | None = None
    systolic: int | None = None
    diastolic: int | None = None
    heart_rate: int | None = None
    context: str | None = Field(default=None, max_length=200)

    @field_validator("context")
    @classmethod
    def _context(cls, value: str | None) -> str | None:
        return " ".join(value.split()) or None if value else None
