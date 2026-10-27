"""Allow a journal to cite an immutable PDF from the instruction library.

Revision ID: b9c4e1a7d206
Revises: a2d7e9c1f605
"""

from alembic import op
import sqlalchemy as sa


revision = "b9c4e1a7d206"
down_revision = "a2d7e9c1f605"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("safety_journal_draft") as batch:
        batch.add_column(sa.Column("library_item_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("subject", sa.String(120), nullable=True))
    with op.batch_alter_table("safety_journal_page") as batch:
        batch.add_column(sa.Column("library_item_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("subject_snapshot", sa.String(120), nullable=True))
        batch.alter_column("instruction_version_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM safety_journal_page WHERE instruction_version_id IS NULL")).scalar():
        raise RuntimeError("Cannot downgrade while journals cite library PDFs.")
    with op.batch_alter_table("safety_journal_page") as batch:
        batch.alter_column("instruction_version_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("subject_snapshot")
        batch.drop_column("library_item_id")
    with op.batch_alter_table("safety_journal_draft") as batch:
        batch.drop_column("subject")
        batch.drop_column("library_item_id")
