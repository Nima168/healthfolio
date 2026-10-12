"""profile details: vitals, allergy type and reaction, surgeries, hospitalizations, family history, medicine kind

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-13 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_FIELDS = "field IN ('date_of_birth', 'sex', 'blood_group', 'height', 'weight', 'allergy')"
_NEW_FIELDS = (
    "field IN ('date_of_birth', 'sex', 'blood_group', 'height', 'weight', 'blood_pressure', 'heart_rate', 'allergy')"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("ck_profile_values_field", "profile_values", type_="check")
    op.create_check_constraint("ck_profile_values_field", "profile_values", _NEW_FIELDS)
    op.add_column("profile_values", sa.Column("category", sa.String(length=20), nullable=True))
    op.add_column("profile_values", sa.Column("detail", sa.String(length=300), nullable=True))
    op.create_check_constraint(
        "ck_profile_values_category",
        "profile_values",
        "category IS NULL OR category IN ('drug', 'food', 'environmental', 'other')",
    )
    op.create_table(
        "medical_record_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("relation", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('surgery', 'hospitalization', 'family')", name="ck_medical_record_items_kind"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medical_record_items_user_kind", "medical_record_items", ["user_id", "kind"], unique=False)
    op.add_column(
        "medications",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="prescription"),
    )
    op.alter_column("medications", "kind", server_default=None)
    op.create_check_constraint(
        "ck_medications_kind", "medications", "kind IN ('prescription', 'over_the_counter', 'supplement')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_medications_kind", "medications", type_="check")
    op.drop_column("medications", "kind")
    op.drop_index("ix_medical_record_items_user_kind", table_name="medical_record_items")
    op.drop_table("medical_record_items")
    op.drop_constraint("ck_profile_values_category", "profile_values", type_="check")
    op.drop_column("profile_values", "detail")
    op.drop_column("profile_values", "category")
    op.execute("DELETE FROM profile_value_history WHERE field IN ('blood_pressure', 'heart_rate')")
    op.execute("DELETE FROM profile_values WHERE field IN ('blood_pressure', 'heart_rate')")
    op.drop_constraint("ck_profile_values_field", "profile_values", type_="check")
    op.create_check_constraint("ck_profile_values_field", "profile_values", _OLD_FIELDS)
