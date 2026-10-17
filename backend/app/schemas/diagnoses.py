"""Diagnoses and Conditions (api_contract_spec.md Section 6.14)."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel

IssueKind = Literal["diagnosis", "assessment", "impression"]


class MentionResponse(BaseModel):
    text: str  # exactly as written in the document
    kind: IssueKind
    document_id: uuid.UUID
    document_title: str | None
    date: date | None


class HealthIssueResponse(BaseModel):
    name: str  # the most recent wording
    kinds: list[IssueKind]
    first_seen: date | None
    last_seen: date | None
    profile: Literal["in_profile", "to_review", "not_in_profile"]
    condition_status: Literal["active", "resolved", "unknown"] | None
    normal: bool  # a finding that reports nothing wrong ("Normal heart size."); shown apart
    mentions: list[MentionResponse]  # newest first


class HealthIssueList(BaseModel):
    items: list[HealthIssueResponse]
