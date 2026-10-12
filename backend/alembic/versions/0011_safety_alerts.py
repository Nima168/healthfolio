"""safety rules, alerts, and alert history; seeds the out-of-range rule

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-12 21:00:00.000000

Rules change only through migrations (backend_spec.md Section 7.5, controlled change management).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUT_OF_RANGE_RULE_ID = "6f1d0b8e-0c4a-4f7e-9a51-2b7c3e5d0a11"


def upgrade() -> None:
    """Upgrade schema."""
    safety_rules = op.create_table(
        "safety_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.String(length=200), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("severity IN ('info', 'warning', 'urgent')", name="ck_safety_rules_severity"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_safety_rules_code_version", "safety_rules", ["code", "version"], unique=True)
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_key", sa.String(length=600), nullable=False),
        sa.Column("input_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("uncertainty", sa.Text(), nullable=True),
        sa.Column("next_steps", sa.Text(), nullable=False),
        sa.Column("explanation_text", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=10), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("severity IN ('info', 'warning', 'urgent')", name="ck_alerts_severity"),
        sa.CheckConstraint("status IN ('open', 'acknowledged', 'resolved')", name="ck_alerts_status"),
        sa.CheckConstraint("resolved_by IS NULL OR resolved_by IN ('user', 'system')", name="ck_alerts_resolved_by"),
        sa.ForeignKeyConstraint(["rule_id"], ["safety_rules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_alerts_user_rule_input", "alerts", ["user_id", "rule_id", "input_key"], unique=True)
    op.create_index("ix_alerts_user_status", "alerts", ["user_id", "status"], unique=False)
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(length=20), nullable=False),
        sa.Column("actor", sa.String(length=10), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event IN ('raised', 'acknowledged', 'resolved', 'reopened')", name="ck_alert_events_event"),
        sa.CheckConstraint("actor IN ('user', 'system')", name="ck_alert_events_actor"),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_events_alert", "alert_events", ["alert_id", "occurred_at"], unique=False)

    op.bulk_insert(
        safety_rules,
        [
            {
                "id": OUT_OF_RANGE_RULE_ID,
                "code": "RESULT_OUTSIDE_REPORT_RANGE",
                "version": 1,
                "description": "A result is outside the reference range printed on the same report; for review.",
                "criteria": {
                    "inputs": ["lab results", "discharge-summary results", "test-report measurements"],
                    "condition": "plain-number value outside the reference range printed on the same report "
                    "(inclusive 'a - b'; '<', '<=', '>', '>=' applied exactly)",
                    "excluded": "no printed range, non-numeric value, unreadable range, or unclear reading",
                    "discharge_summaries": "only the last value of each test",
                    "not_used": "clinical thresholds, other reports' ranges, trends across dates",
                },
                "severity": "warning",
                "source_reference": "goal_spec.md F-9; backend_spec.md Section 7.5; DL_AI_spec.md Section 9.1",
                "approved_by": "Project specification (clinical review required before production use)",
                "approved_at": datetime(2026, 10, 12, tzinfo=UTC),
                "active": True,
            }
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_alert_events_alert", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index("ix_alerts_user_status", table_name="alerts")
    op.drop_index("uq_alerts_user_rule_input", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("uq_safety_rules_code_version", table_name="safety_rules")
    op.drop_table("safety_rules")
