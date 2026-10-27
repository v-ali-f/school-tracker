"""Allow teachers to prepare trip journals without an order record.

Revision ID: c7e2a9d4f105
Revises: b9c4e1a7d206
"""

from alembic import op
import sqlalchemy as sa


revision = "c7e2a9d4f105"
down_revision = "b9c4e1a7d206"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("safety_journal_draft") as batch:
        batch.add_column(sa.Column("journal_kind", sa.String(20), nullable=False, server_default="ordinary"))
        batch.add_column(sa.Column("manual_trip", sa.JSON(), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM safety_journal_draft WHERE journal_kind = 'trip' AND trip_order_id IS NULL")).scalar():
        raise RuntimeError("Cannot downgrade while standalone trip drafts exist.")
    with op.batch_alter_table("safety_journal_draft") as batch:
        batch.drop_column("manual_trip")
        batch.drop_column("journal_kind")
