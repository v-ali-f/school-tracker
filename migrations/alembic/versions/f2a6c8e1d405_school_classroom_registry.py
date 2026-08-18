"""Add the school classroom registry.

Revision ID: f2a6c8e1d405
Revises: e1f4a8c2d690
"""

from alembic import op
import sqlalchemy as sa


revision = "f2a6c8e1d405"
down_revision = "e1f4a8c2d690"
branch_labels = None
depends_on = None

TABLE_NAME = "school_classroom"


def upgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("short_name", sa.String(length=50), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("teacher_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "capacity IS NULL OR capacity > 0",
            name="ck_school_classroom_capacity_positive",
        ),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["buildings.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_user_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "building_id",
            "name",
            name="uq_school_classroom_building_name",
        ),
        sa.UniqueConstraint(
            "building_id",
            "teacher_user_id",
            name="uq_school_classroom_teacher_building",
        ),
    )
    for column_name in ("building_id", "teacher_user_id", "is_active"):
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
    for column_name in ("is_active", "teacher_user_id", "building_id"):
        op.drop_index(
            f"ix_{TABLE_NAME}_{column_name}",
            table_name=TABLE_NAME,
        )
    op.drop_table(TABLE_NAME)
