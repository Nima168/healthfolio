"""AI summary responses (api_contract_spec.md Section 6.12)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SummarySentence(BaseModel):
    text: str
    kind: Literal["record", "interpretation"]
    fact_ids: list[str]


class SummarySection(BaseModel):
    key: str
    title: str
    sentences: list[SummarySentence]


class Explanation(BaseModel):
    """General medical knowledge, not drawn from the user's records."""

    term: str
    text: str
    fact_ids: list[str]


class Insight(BaseModel):
    """A gap or item to review found by fixed rules (not by the AI)."""

    id: str
    text: str
    link: str | None


class SourceRef(BaseModel):
    kind: str
    title: str
    date: str | None
    trust: str | None
    source_document_id: uuid.UUID | None
    source_document_title: str | None
    link: str | None


class SummaryView(BaseModel):
    id: uuid.UUID
    scope: Literal["history", "document"]
    created_at: datetime
    model_version: str
    sections: list[SummarySection]
    explanations: list[Explanation]
    insights: list[Insight]
    sources: dict[str, SourceRef]
    dropped_count: int


class SummaryState(BaseModel):
    enabled: bool  # AI is switched on for this server
    can_create: bool  # there are records (history) or the document has been read
    summary: SummaryView | None
    stale: bool  # the records changed after this summary was written
