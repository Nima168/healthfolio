"""email: a "disabled" provider for deployments without an email service

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-14 18:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_email_deliveries_provider", "email_deliveries", type_="check")
    op.create_check_constraint(
        "ck_email_deliveries_provider", "email_deliveries", "provider IN ('file', 'ses', 'disabled')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM email_deliveries WHERE provider = 'disabled'")
    op.drop_constraint("ck_email_deliveries_provider", "email_deliveries", type_="check")
    op.create_check_constraint("ck_email_deliveries_provider", "email_deliveries", "provider IN ('file', 'ses')")
