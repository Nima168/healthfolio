"""processing_jobs: document kinds pathology_report and specialist_report

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-17 22:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = (
    "document_kind IS NULL OR document_kind IN ('lab_report', 'prescription', 'discharge_summary', "
    "'consultation_note', 'imaging_report', 'test_report', 'other')"
)
NEW = OLD.replace("'test_report', 'other'", "'test_report', 'pathology_report', 'specialist_report', 'other'")


def upgrade() -> None:
    # Only the allowed values change; no reading is altered here.
    op.drop_constraint("ck_processing_jobs_document_kind", "processing_jobs", type_="check")
    op.create_check_constraint("ck_processing_jobs_document_kind", "processing_jobs", NEW)


def downgrade() -> None:
    op.execute(
        "UPDATE processing_jobs SET document_kind = 'other' "
        "WHERE document_kind IN ('pathology_report', 'specialist_report')"
    )
    op.drop_constraint("ck_processing_jobs_document_kind", "processing_jobs", type_="check")
    op.create_check_constraint("ck_processing_jobs_document_kind", "processing_jobs", OLD)
