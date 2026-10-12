"""remove result review

Extracted results are shown as read; the confirm / correct / reject step is removed.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-11 17:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f("ix_observation_corrections_observation_id"), table_name="observation_corrections")
    op.drop_table("observation_corrections")
    op.drop_constraint("ck_observations_review_status", "observations", type_="check")
    op.drop_column("observations", "reviewed_at")
    op.drop_column("observations", "review_status")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "observations",
        sa.Column("review_status", sa.String(length=20), nullable=False, server_default="unconfirmed"),
    )
    op.alter_column("observations", "review_status", server_default=None)
    op.add_column("observations", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_observations_review_status",
        "observations",
        "review_status IN ('unconfirmed', 'confirmed', 'corrected', 'rejected')",
    )
    op.create_table(
        "observation_corrections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("field", sa.String(length=50), nullable=False),
        sa.Column("previous_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_observation_corrections_observation_id"), "observation_corrections", ["observation_id"], unique=False
    )
