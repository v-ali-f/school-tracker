"""Add immutable history for teacher professional records.

Revision ID: e1f4a8c2d690
Revises: d9b6f2c4a810
"""

from alembic import op
import sqlalchemy as sa


revision = "e1f4a8c2d690"
down_revision = "d9b6f2c4a810"
branch_labels = None
depends_on = None

TABLE_NAME = "teacher_professional_record_change"


def upgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("record_type", sa.String(length=24), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("change_kind", sa.String(length=24), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["teacher_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column_name in (
        "record_type",
        "record_id",
        "teacher_id",
        "change_kind",
        "changed_by_user_id",
    ):
        op.create_index(
            f"ix_{TABLE_NAME}_{column_name}",
            TABLE_NAME,
            [column_name],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE_NAME):
        return
    for column_name in (
        "changed_by_user_id",
        "change_kind",
        "teacher_id",
        "record_id",
        "record_type",
    ):
        op.drop_index(
            f"ix_{TABLE_NAME}_{column_name}",
            table_name=TABLE_NAME,
        )
    op.drop_table(TABLE_NAME)
