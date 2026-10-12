"""Medications, conditions, follow-up suggestions, and follow-ups (data_model_spec.md Sections 5.4–5.7)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.auth import TimestampMixin
from app.models.document import _in
from app.models.extraction import CONFIDENCE_LEVELS, ORIGINS

MEDICATION_STATUSES = ("active", "stopped", "unknown")
CONDITION_STATUSES = ("active", "resolved", "unknown")
FOLLOW_UP_KINDS = ("investigation", "appointment", "checkup")
SUGGESTION_TYPES = ("follow_up",)
SUGGESTION_STATUSES = ("pending", "accepted", "rejected", "superseded")
FOLLOW_UP_STATUSES = ("scheduled", "completed", "cancelled")
DUE_DATE_BASES = ("written", "calculated")
_CONFIDENCE = f"confidence IS NULL OR {_in('confidence', CONFIDENCE_LEVELS)}"


class Medication(TimestampMixin, Base):
    """A medicine as written on a prescription. Status is never inferred as active from a document."""

    __tablename__ = "medications"
    __table_args__ = (
        CheckConstraint(_in("status", MEDICATION_STATUSES), name="ck_medications_status"),
        CheckConstraint(_in("origin", ORIGINS), name="ck_medications_origin"),
        CheckConstraint(_CONFIDENCE, name="ck_medications_confidence"),
        Index("ix_medications_document", "source_document_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
    processing_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    strength: Mapped[str | None] = mapped_column(String(100))
    dosage_text: Mapped[str | None] = mapped_column(String(300))  # how and when to take it, as written
    duration_text: Mapped[str | None] = mapped_column(String(100))
    prescriber_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    origin: Mapped[str] = mapped_column(String(32), default="document_extracted", nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(10))
    review_reason: Mapped[str | None] = mapped_column(Text)  # set when the item must be checked, not judged
    source_location: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Condition(TimestampMixin, Base):
    """A diagnosis exactly as written in a document. Status is never inferred (always "unknown" from a document)."""

    __tablename__ = "conditions"
    __table_args__ = (
        CheckConstraint(_in("status", CONDITION_STATUSES), name="ck_conditions_status"),
        CheckConstraint(_in("origin", ORIGINS), name="ck_conditions_origin"),
        Index("ix_conditions_document", "source_document_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
    processing_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    origin: Mapped[str] = mapped_column(String(32), default="document_extracted", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Suggestion(TimestampMixin, Base):
    """Something found in a document that becomes a record only when the user accepts it."""

    __tablename__ = "suggestions"
    __table_args__ = (
        CheckConstraint(_in("suggestion_type", SUGGESTION_TYPES), name="ck_suggestions_type"),
        CheckConstraint(_in("status", SUGGESTION_STATUSES), name="ck_suggestions_status"),
        CheckConstraint(f"kind IS NULL OR {_in('kind', FOLLOW_UP_KINDS)}", name="ck_suggestions_kind"),
        CheckConstraint(
            f"due_date_basis IS NULL OR {_in('due_date_basis', DUE_DATE_BASES)}", name="ck_suggestions_due_basis"
        ),
        CheckConstraint(_CONFIDENCE, name="ck_suggestions_confidence"),
        Index("ix_suggestions_document", "source_document_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    suggestion_type: Mapped[str] = mapped_column(String(32), default="follow_up", nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
    processing_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    suggested_value: Mapped[str] = mapped_column(String(300), nullable=False)  # e.g. "Kidney function test"
    kind: Mapped[str | None] = mapped_column(String(20))
    original_text: Mapped[str | None] = mapped_column(String(200))  # the timing as written
    due_date: Mapped[date | None] = mapped_column(Date)
    due_date_basis: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[str | None] = mapped_column(String(10))
    review_reason: Mapped[str | None] = mapped_column(Text)
    source_location: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # the follow-up created on acceptance


class FollowUp(TimestampMixin, Base):
    """A checkup, test, or appointment the user tracks. "Overdue" is computed, never stored."""

    __tablename__ = "follow_ups"
    __table_args__ = (
        CheckConstraint(_in("kind", FOLLOW_UP_KINDS), name="ck_follow_ups_kind"),
        CheckConstraint(_in("status", FOLLOW_UP_STATUSES), name="ck_follow_ups_status"),
        CheckConstraint(_in("origin", ORIGINS), name="ck_follow_ups_origin"),
        Index("ix_follow_ups_user_due", "user_id", "status", "due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="checkup", nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origin: Mapped[str] = mapped_column(String(32), default="user_entered", nullable=False)
    suggestion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suggestions.id", ondelete="SET NULL"))
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
