"""Medical documents (data_model_spec.md Section 5.1)."""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.auth import TimestampMixin

DOCUMENT_CATEGORIES = (
    "lab_report",
    "prescription",
    "discharge_summary",
    "consultation_note",
    "imaging_report",
    "other",
    "unknown",
)
DATE_PRECISIONS = ("day", "month", "year", "unknown")
MEDIA_TYPES = ("application/pdf", "image/jpeg", "image/png")
PROCESSING_STATUSES = ("pending", "running", "completed", "completed_with_warnings", "failed", "cancelled")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(_in("category", DOCUMENT_CATEGORIES), name="ck_documents_category"),
        CheckConstraint(_in("media_type", MEDIA_TYPES), name="ck_documents_media_type"),
        CheckConstraint(_in("processing_status", PROCESSING_STATUSES), name="ck_documents_processing_status"),
        CheckConstraint(
            f"document_date_precision IS NULL OR {_in('document_date_precision', DATE_PRECISIONS)}",
            name="ck_documents_date_precision",
        ),
        # Duplicate detection only among live documents, so a deleted file can be uploaded again.
        Index(
            "uq_documents_user_sha256_live",
            "user_id",
            "sha256",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_documents_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    # Nullable fields below are cleared when the document becomes a tombstone.
    storage_key: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(200))  # user-given name; required by the API
    original_filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(200))
    document_date: Mapped[date | None] = mapped_column(Date)
    document_date_precision: Mapped[str | None] = mapped_column(String(10))
    processing_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
