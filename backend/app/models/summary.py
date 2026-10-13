"""AI summaries of the user's records (data_model_spec.md Section 5.9)."""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.auth import TimestampMixin
from app.models.document import _in

SUMMARY_SCOPES = ("history", "document")


class AiSummary(TimestampMixin, Base):
    """One generated summary. A newer one replaces it on screen; deleting a document removes those that used it."""

    __tablename__ = "ai_summaries"
    __table_args__ = (
        CheckConstraint(_in("scope", SUMMARY_SCOPES), name="ck_ai_summaries_scope"),
        CheckConstraint("(scope = 'document') = (document_id IS NOT NULL)", name="ck_ai_summaries_document"),
        Index("ix_ai_summaries_user_scope", "user_id", "scope", "document_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
    # Checked sentences by section; each cites the facts it rests on.
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # The facts given to the model, by id: what each citation points to.
    source_refs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # General-knowledge explanations (DL_AI_spec.md Section 6.1), kept apart from record-based text.
    general_knowledge_sections: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    # Gaps found by fixed rules, shown as they were when the summary was written.
    insights: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    dropped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)  # of the facts: "records changed" check
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
