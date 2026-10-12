"""Processing jobs and extracted observations (data_model_spec.md Sections 5.2 and 5.3)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.auth import TimestampMixin, utcnow
from app.models.document import DATE_PRECISIONS, PROCESSING_STATUSES, _in

JOB_KINDS = ("extraction",)
ACTIVE_JOB_STATUSES = ("pending", "running")
CONFIDENCE_LEVELS = ("high", "medium", "low")
ORIGINS = ("user_entered", "document_extracted", "suggestion_accepted")


class ProcessingJob(TimestampMixin, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(_in("kind", JOB_KINDS), name="ck_processing_jobs_kind"),
        CheckConstraint(_in("status", PROCESSING_STATUSES), name="ck_processing_jobs_status"),
        CheckConstraint(
            "document_kind IS NULL OR document_kind IN ('lab_report', 'prescription', 'discharge_summary', "
            "'consultation_note', 'imaging_report', 'test_report', 'other')",
            name="ck_processing_jobs_document_kind",
        ),
        # At most one waiting/running job of a kind per document.
        Index(
            "uq_processing_jobs_active",
            "document_id",
            "kind",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
        # The worker's claim query: oldest runnable pending job first.
        Index("ix_processing_jobs_claim", "status", "run_after", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="extraction", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    stage: Mapped[str | None] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(80))  # "classify-…+prescription-…" when classified
    # What the document was read as: the user's chosen type, or the AI's classification when none was chosen.
    document_kind: Mapped[str | None] = mapped_column(String(20))
    report_date_text: Mapped[str | None] = mapped_column(String(100))  # report/prescription date exactly as printed
    document_date: Mapped[date | None] = mapped_column(Date)  # the prescription date, as a date
    prescriber_name: Mapped[str | None] = mapped_column(String(200))
    # Kind-specific facts kept as written: discharge (facility, stay, warning signs), consultation,
    # imaging, and other test reports (app/ai/report_validation.py).
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Observation(TimestampMixin, Base):
    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint("kind IN ('lab_result', 'vital_sign', 'other')", name="ck_observations_kind"),
        CheckConstraint(_in("origin", ORIGINS), name="ck_observations_origin"),
        CheckConstraint(
            f"confidence IS NULL OR {_in('confidence', CONFIDENCE_LEVELS)}", name="ck_observations_confidence"
        ),
        CheckConstraint(
            f"observed_at_precision IS NULL OR {_in('observed_at_precision', DATE_PRECISIONS)}",
            name="ck_observations_date_precision",
        ),
        Index("ix_observations_document", "source_document_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
    processing_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), default="lab_result", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # order within the source document
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    value_text: Mapped[str] = mapped_column(String(200), nullable=False)  # exactly as written
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    unit: Mapped[str | None] = mapped_column(String(50))
    reference_range_text: Mapped[str | None] = mapped_column(String(200))
    reference_low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    reference_high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    observed_at: Mapped[date | None] = mapped_column(Date)
    observed_at_precision: Mapped[str | None] = mapped_column(String(10))
    # {"page": int | null, "snippet": str | null}: where in the original the value was found.
    source_location: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    origin: Mapped[str] = mapped_column(String(32), default="document_extracted", nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(10))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validation_findings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
