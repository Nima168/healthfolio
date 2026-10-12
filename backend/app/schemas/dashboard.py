"""Dashboard schemas (api_contract_spec.md Section 6.11)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.profile import LatestVitalResponse
from app.schemas.timeline import TimelineEntryResponse


class DashboardDocument(BaseModel):
    id: uuid.UUID
    title: str | None
    category: str
    uploaded_at: datetime
    # Latest reading: pending, running, completed, completed_with_warnings, failed, cancelled; null if never read.
    reading_status: str | None
    read_as: str | None  # the kind of report it was read as


class DashboardFollowUp(BaseModel):
    id: uuid.UUID
    title: str
    due_date: date
    source_document_id: uuid.UUID | None


class DashboardAlert(BaseModel):
    id: uuid.UUID
    title: str
    severity: Literal["info", "warning", "urgent"]
    source_document_title: str | None


class DocumentCount(BaseModel):
    id: uuid.UUID
    title: str | None
    count: int


class DashboardResponse(BaseModel):
    documents_total: int
    documents_reading: int
    recent_documents: list[DashboardDocument]
    overdue_follow_ups: list[DashboardFollowUp]
    upcoming_follow_ups: list[DashboardFollowUp]  # due within 30 days
    alerts_open: int
    alerts_acknowledged: int
    alerts_urgent: int
    top_alerts: list[DashboardAlert]  # urgent first, at most 3
    profile_suggestions: int
    unconfirmed_medicines: int
    follow_ups_to_add: list[DocumentCount]
    failed_documents: list[DocumentCount]
    profile_filled: int
    profile_total: int
    profile_missing: list[str]
    allergies: list[str]
    conditions: int
    active_medications: int
    bmi: float | None
    bmi_category: str | None
    latest_blood_pressure: LatestVitalResponse | None
    latest_heart_rate: LatestVitalResponse | None
    recent_activity: list[TimelineEntryResponse]
