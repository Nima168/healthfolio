"""vital sign readings: dated blood pressure and heart rate

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-13 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "vital_readings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("measured_time", sa.Time(), nullable=True),
        sa.Column("systolic", sa.Integer(), nullable=True),
        sa.Column("diastolic", sa.Integer(), nullable=True),
        sa.Column("heart_rate", sa.Integer(), nullable=True),
        sa.Column("context", sa.String(length=200), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "systolic IS NOT NULL OR heart_rate IS NOT NULL", name="ck_vital_readings_something_measured"
        ),
        sa.CheckConstraint("(systolic IS NULL) = (diastolic IS NULL)", name="ck_vital_readings_pressure_pair"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vital_readings_user_measured", "vital_readings", ["user_id", "measured_on"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_vital_readings_user_measured", table_name="vital_readings")
    op.drop_table("vital_readings")
