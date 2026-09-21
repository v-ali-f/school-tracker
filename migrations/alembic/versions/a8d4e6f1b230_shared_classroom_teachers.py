"""Allow several teachers per classroom and several rooms per teacher.

Revision ID: a8d4e6f1b230
Revises: f2a6c8e1d405
"""

from alembic import op
import sqlalchemy as sa


revision = "a8d4e6f1b230"
down_revision = "f2a6c8e1d405"
branch_labels = None
depends_on = None

LINK_TABLE = "school_classroom_teacher"
LEGACY_CONSTRAINT = "uq_school_classroom_teacher_building"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(LINK_TABLE):
        op.create_table(
            LINK_TABLE,
            sa.Column("classroom_id", sa.Integer(), nullable=False),
            sa.Column("teacher_user_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ["classroom_id"],
                ["school_classroom.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["teacher_user_id"],
                ["user.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("classroom_id", "teacher_user_id"),
        )
        op.create_index(
            "ix_school_classroom_teacher_teacher_user_id",
            LINK_TABLE,
            ["teacher_user_id"],
            unique=False,
        )

    insert_prefix = (
        "INSERT OR IGNORE"
        if bind.dialect.name == "sqlite"
        else "INSERT"
    )
    conflict_suffix = "" if bind.dialect.name == "sqlite" else (
        " ON CONFLICT DO NOTHING"
    )
    op.execute(sa.text(
        f"{insert_prefix} INTO school_classroom_teacher "
        "(classroom_id, teacher_user_id) "
        "SELECT id, teacher_user_id FROM school_classroom "
        "WHERE teacher_user_id IS NOT NULL"
        f"{conflict_suffix}"
    ))

    unique_constraints = {
        item.get("name")
        for item in inspector.get_unique_constraints("school_classroom")
    }
    if LEGACY_CONSTRAINT in unique_constraints:
        op.drop_constraint(
            LEGACY_CONSTRAINT,
            "school_classroom",
            type_="unique",
        )


def downgrade():
    op.create_unique_constraint(
        LEGACY_CONSTRAINT,
        "school_classroom",
        ["building_id", "teacher_user_id"],
    )
    op.drop_index(
        "ix_school_classroom_teacher_teacher_user_id",
        table_name=LINK_TABLE,
    )
    op.drop_table(LINK_TABLE)
