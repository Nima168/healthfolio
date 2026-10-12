"""Safety alert schemas (api_contract_spec.md Section 6.8)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AlertStatus = Literal["open", "acknowledged", "resolved"]


class AlertEventResponse(BaseModel):
    event: Literal["raised", "acknowledged", "resolved", "reopened"]
    actor: Literal["user", "system"]
    note: str | None
    occurred_at: datetime


class AlertResponse(BaseModel):
    id: uuid.UUID
    rule_code: str
    rule_version: int
    rule_description: str
    severity: Literal["info", "warning", "urgent"]
    status: AlertStatus
    title: str
    reason: str  # rule-based, deterministic
    uncertainty: str | None
    next_steps: str
    explanation_text: str | None  # AI, labelled; not generated yet
    source_document_id: uuid.UUID | None
    source_document_title: str | None  # null when the document was deleted
    # How the report was read (or its upload type), and its own date; null when unknown or deleted.
    report_type: str | None
    report_date: date | None
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolved_by: Literal["user", "system"] | None
    resolution_note: str | None
    history: list[AlertEventResponse]


class AlertListResponse(BaseModel):
    items: list[AlertResponse]


class AlertUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["acknowledged", "resolved"]
    note: str | None = Field(default=None, max_length=1000)
