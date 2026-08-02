"""Add applications count to school classes.

Revision ID: f8b0c4e6a123
Revises: e7a9b3d5f012
"""

from alembic import op
import sqlalchemy as sa


revision = "f8b0c4e6a123"
down_revision = "e7a9b3d5f012"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("school_class") as batch_op:
        batch_op.add_column(
            sa.Column(
                "applications_count",
                sa.Integer(),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_school_class_applications_nonnegative",
            "applications_count >= 0",
        )


def downgrade():
    with op.batch_alter_table("school_class") as batch_op:
        batch_op.drop_constraint(
            "ck_school_class_applications_nonnegative",
            type_="check",
        )
        batch_op.drop_column("applications_count")
