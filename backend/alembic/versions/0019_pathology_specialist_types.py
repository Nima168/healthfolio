"""documents: report types pathology_report and specialist_report

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-17 20:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "'lab_report', 'prescription', 'discharge_summary', 'consultation_note', 'imaging_report', 'other', 'unknown'"
NEW = OLD.replace("'other'", "'pathology_report', 'specialist_report', 'other'")


def upgrade() -> None:
    # Only the allowed values change; no document is altered here.
    op.drop_constraint("ck_documents_category", "documents", type_="check")
    op.create_check_constraint("ck_documents_category", "documents", f"category IN ({NEW})")


def downgrade() -> None:
    op.execute("UPDATE documents SET category = 'other' WHERE category IN ('pathology_report', 'specialist_report')")
    op.drop_constraint("ck_documents_category", "documents", type_="check")
    op.create_check_constraint("ck_documents_category", "documents", f"category IN ({OLD})")
