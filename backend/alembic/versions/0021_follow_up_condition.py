"""suggestions: the written condition of a follow-up ("if not better / SOS")

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-17 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: follow-ups read before this keep no condition until read again.
    op.add_column("suggestions", sa.Column("condition_text", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("suggestions", "condition_text")
