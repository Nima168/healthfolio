"""ocr reading: the document's copy type, and how each reading obtained the text

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-14 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("documents", sa.Column("copy_type", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        "ck_documents_copy_type", "documents", "copy_type IS NULL OR copy_type IN ('digital', 'scanned')"
    )
    # Photos are always scanned copies; PDFs uploaded earlier stay unknown (detected from the file).
    op.execute("UPDATE documents SET copy_type = 'scanned' WHERE media_type IN ('image/jpeg', 'image/png')")
    op.add_column("processing_jobs", sa.Column("reading_method", sa.String(length=20), nullable=True))
    op.add_column("processing_jobs", sa.Column("ocr_confidence", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("processing_jobs", "ocr_confidence")
    op.drop_column("processing_jobs", "reading_method")
    op.drop_constraint("ck_documents_copy_type", "documents", type_="check")
    op.drop_column("documents", "copy_type")
