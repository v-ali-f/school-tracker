"""Store the briefing kind selected for each journal page.

Revision ID: a2d7e9c1f605
Revises: f0b7c4a8d219
"""

from alembic import op
import sqlalchemy as sa


revision = "a2d7e9c1f605"
down_revision = "f0b7c4a8d219"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("safety_journal_draft") as batch:
        batch.add_column(sa.Column("briefing_kind", sa.String(80), nullable=True))
        batch.add_column(sa.Column("header_note", sa.String(500), nullable=True))
    with op.batch_alter_table("safety_journal_page") as batch:
        batch.add_column(sa.Column("briefing_kind_snapshot", sa.String(80), nullable=True))
        batch.add_column(sa.Column("header_note_snapshot", sa.String(500), nullable=True))


def downgrade():
    with op.batch_alter_table("safety_journal_page") as batch:
        batch.drop_column("header_note_snapshot")
        batch.drop_column("briefing_kind_snapshot")
    with op.batch_alter_table("safety_journal_draft") as batch:
        batch.drop_column("header_note")
        batch.drop_column("briefing_kind")
