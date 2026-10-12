"""Safety rules and the alerts they raise (data_model_spec.md Section 5.8, backend_spec.md Section 7.5).

Rules decide; AI may only explain. Rules are global and change only through migrations (controlled change).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.auth import TimestampMixin
from app.models.document import _in

SEVERITIES = ("info", "warning", "urgent")
ALERT_STATUSES = ("open", "acknowledged", "resolved")
RESOLVERS = ("user", "system")


class SafetyRule(Base):
    __tablename__ = "safety_rules"
    __table_args__ = (
        CheckConstraint(_in("severity", SEVERITIES), name="ck_safety_rules_severity"),
        Index("uq_safety_rules_code_version", "code", "version", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # deterministic, documented
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str] = mapped_column(String(200), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Alert(TimestampMixin, Base):
    """One raised alert. `input_key` identifies the triggering record by content, so reading a document again
    keeps the same alert (and the user's acknowledgement) instead of raising a new one."""

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(_in("severity", SEVERITIES), name="ck_alerts_severity"),
        CheckConstraint(_in("status", ALERT_STATUSES), name="ck_alerts_status"),
        CheckConstraint(f"resolved_by IS NULL OR {_in('resolved_by', RESOLVERS)}", name="ck_alerts_resolved_by"),
        Index("uq_alerts_user_rule_input", "user_id", "rule_id", "input_key", unique=True),
        Index("ix_alerts_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("safety_rules.id", ondelete="RESTRICT"), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    input_key: Mapped[str] = mapped_column(String(600), nullable=False)
    input_refs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)  # rule-based, deterministic wording
    uncertainty: Mapped[str | None] = mapped_column(Text)
    next_steps: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_text: Mapped[str | None] = mapped_column(Text)  # AI, labelled; not generated yet
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(10))
    resolution_note: Mapped[str | None] = mapped_column(Text)


ALERT_EVENTS = ("raised", "acknowledged", "resolved", "reopened")


class AlertEvent(Base):
    """The alert's lifecycle history, oldest first. Never edited."""

    __tablename__ = "alert_events"
    __table_args__ = (
        CheckConstraint(_in("event", ALERT_EVENTS), name="ck_alert_events_event"),
        CheckConstraint(_in("actor", RESOLVERS), name="ck_alert_events_actor"),
        Index("ix_alert_events_alert", "alert_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=False)
    event: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(String(10), nullable=False)  # user or system
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
