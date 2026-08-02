"""Add individual workload editor access.

Revision ID: e3b7c1d9a524
Revises: a9c4e7f1b203
"""

from alembic import op
import sqlalchemy as sa


revision = "e3b7c1d9a524"
down_revision = "a9c4e7f1b203"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workload_editor_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.UniqueConstraint("user_id", name="uq_workload_editor_access_user"),
    )
    op.create_index(
        "ix_workload_editor_access_user_id",
        "workload_editor_access",
        ["user_id"],
    )
    op.create_index(
        "ix_workload_editor_access_is_active",
        "workload_editor_access",
        ["is_active"],
    )


def downgrade():
    op.drop_index(
        "ix_workload_editor_access_is_active",
        table_name="workload_editor_access",
    )
    op.drop_index(
        "ix_workload_editor_access_user_id",
        table_name="workload_editor_access",
    )
    op.drop_table("workload_editor_access")
