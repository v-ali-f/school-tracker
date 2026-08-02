"""Add profile name to education plan bundles.

Revision ID: e7a9b3d5f012
Revises: d6f8a2c4e901
"""

from alembic import op
import sqlalchemy as sa


revision = "e7a9b3d5f012"
down_revision = "d6f8a2c4e901"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("education_plan") as batch_op:
        batch_op.add_column(
            sa.Column("profile_name", sa.String(length=160), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("education_plan") as batch_op:
        batch_op.drop_column("profile_name")
