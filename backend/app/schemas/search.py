"""Record search schemas (api_contract_spec.md Section 9.1)."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RecordType = Literal[
    "document",
    "report_text",
    "lab_result",
    "medication",
    "diagnosis",
    "condition",
    "follow_up",
    "allergy",
    "surgery",
    "hospitalization",
    "family_history",
]


class SearchRequest(BaseModel):
    """Sent as a POST body so the query text never appears in a logged URL. Criteria combine."""

    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, max_length=200)
    document_type: str | None = Field(default=None, max_length=40)
    date_from: date | None = None
    date_to: date | None = None
    condition: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=12)

    @field_validator("query", "condition", "provider", "document_type")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        return " ".join(value.split()) or None if value else None


class SearchResult(BaseModel):
    record_type: RecordType
    id: str
    title: str
    date: date | None
    matched_field: str | None  # which field matched the query, e.g. "Impression"
    snippet: str | None  # the matching text, shortened
    source_document_id: uuid.UUID | None
    source_document_title: str | None
    link: str


class SearchResponse(BaseModel):
    items: list[SearchResult]
    total: int
    next_cursor: str | None
