"""medication records: user changes, dates, and change history

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-12 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("medications", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("medications", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("medications", sa.Column("status_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("medications", sa.Column("user_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "medication_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("medication_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("change_origin", sa.String(length=20), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "change_origin IN ('added', 'edited', 'status_changed', 'removed')", name="ck_medication_history_change"
        ),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_medication_history_medication", "medication_history", ["medication_id", "changed_at"], unique=False
    )
    op.create_index("ix_medications_user_status", "medications", ["user_id", "status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_medications_user_status", table_name="medications")
    op.drop_index("ix_medication_history_medication", table_name="medication_history")
    op.drop_table("medication_history")
    op.drop_column("medications", "user_updated_at")
    op.drop_column("medications", "status_confirmed_at")
    op.drop_column("medications", "end_date")
    op.drop_column("medications", "start_date")
