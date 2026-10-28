"""Store teacher-entered briefing date and time separately from journal creation.

Revision ID: d8a2e4b7c019
Revises: c7e2a9d4f105
"""

from alembic import op
import sqlalchemy as sa


revision = "d8a2e4b7c019"
down_revision = "c7e2a9d4f105"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("safety_journal_draft") as batch:
        batch.add_column(sa.Column("briefing_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("safety_journal_page") as batch:
        batch.add_column(sa.Column("briefing_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("safety_journal_page") as batch:
        batch.drop_column("briefing_at")
    with op.batch_alter_table("safety_journal_draft") as batch:
        batch.drop_column("briefing_at")
