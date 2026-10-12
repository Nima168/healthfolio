"""Follow-up schemas (api_contract_spec.md Section 6.3)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

FollowUpStatus = Literal["scheduled", "completed", "cancelled"]


class FollowUpResponse(BaseModel):
    id: uuid.UUID
    title: str
    kind: Literal["investigation", "appointment", "checkup"]
    due_date: date
    status: FollowUpStatus
    overdue: bool  # computed: scheduled and the due date has passed
    completed_at: datetime | None
    source_document_id: uuid.UUID | None
    source_document_title: str | None  # null when there is no source or it was deleted


class FollowUpListResponse(BaseModel):
    items: list[FollowUpResponse]


class FollowUpUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FollowUpStatus
