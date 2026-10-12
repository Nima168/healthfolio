"""health profile: profile values with history; condition review for document suggestions

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-12 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "profile_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("suggestion_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "field IN ('date_of_birth', 'sex', 'blood_group', 'height', 'weight', 'allergy')",
            name="ck_profile_values_field",
        ),
        sa.CheckConstraint(
            "origin IN ('user_entered', 'document_extracted', 'suggestion_accepted')", name="ck_profile_values_origin"
        ),
        sa.ForeignKeyConstraint(["suggestion_id"], ["suggestions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profile_values_user_field", "profile_values", ["user_id", "field"], unique=False)
    op.create_table(
        "profile_value_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_value_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("previous_value", sa.String(length=200), nullable=True),
        sa.Column("new_value", sa.String(length=200), nullable=True),
        sa.Column("change_origin", sa.String(length=20), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("change_origin IN ('added', 'changed', 'removed')", name="ck_profile_value_history_change"),
        sa.ForeignKeyConstraint(["profile_value_id"], ["profile_values.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profile_value_history_user", "profile_value_history", ["user_id", "changed_at"], unique=False)
    op.add_column("conditions", sa.Column("review_status", sa.String(length=20), nullable=True))
    op.add_column("conditions", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conditions", sa.Column("profile_condition_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conditions_profile_condition",
        "conditions",
        "conditions",
        ["profile_condition_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_conditions_review",
        "conditions",
        "review_status IS NULL OR review_status IN ('accepted', 'corrected', 'rejected')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_conditions_review", "conditions", type_="check")
    op.drop_constraint("fk_conditions_profile_condition", "conditions", type_="foreignkey")
    op.drop_column("conditions", "profile_condition_id")
    op.drop_column("conditions", "reviewed_at")
    op.drop_column("conditions", "review_status")
    op.drop_index("ix_profile_value_history_user", table_name="profile_value_history")
    op.drop_table("profile_value_history")
    op.drop_index("ix_profile_values_user_field", table_name="profile_values")
    op.drop_table("profile_values")
