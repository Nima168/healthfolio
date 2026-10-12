"""Health timeline schemas (api_contract_spec.md Section 6.7)."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

TimelineCategory = Literal[
    "lab_results",
    "imaging",
    "test_reports",
    "consultations",
    "hospital_stays",
    "prescriptions",
    "medications",
    "follow_ups",
    "vitals",
    "documents",
]


class TimelineEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    date: date | None  # null: no date is known (never guessed)
    date_precision: Literal["day", "month", "year", "unknown"] | None
    category: TimelineCategory
    title: str
    lines: list[str]
    trust: Literal["from_document", "confirmed_by_you", "edited_by_you", "added_by_you"]
    tag: str | None
    source_document_id: uuid.UUID | None
    source_document_title: str | None
    link: str | None


class TimelinePage(BaseModel):
    items: list[TimelineEntryResponse]
    next_cursor: str | None
