"""documents: optional report sub-type

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-17 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable and without a default: documents already uploaded are left unchanged.
    op.add_column("documents", sa.Column("report_subtype", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "report_subtype")
