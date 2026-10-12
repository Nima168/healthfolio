"""more document kinds: consultation_note, imaging_report, test_report

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-12 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_processing_jobs_document_kind"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(_NAME, "processing_jobs", type_="check")
    op.create_check_constraint(
        _NAME,
        "processing_jobs",
        "document_kind IS NULL OR document_kind IN ('lab_report', 'prescription', 'discharge_summary', "
        "'consultation_note', 'imaging_report', 'test_report', 'other')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(_NAME, "processing_jobs", type_="check")
    op.execute(
        "UPDATE processing_jobs SET document_kind = 'other' "
        "WHERE document_kind IN ('consultation_note', 'imaging_report', 'test_report')"
    )
    op.create_check_constraint(
        _NAME,
        "processing_jobs",
        "document_kind IS NULL OR document_kind IN ('lab_report', 'prescription', 'discharge_summary', 'other')",
    )
