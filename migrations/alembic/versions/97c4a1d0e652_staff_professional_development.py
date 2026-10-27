"""Imported professional development courses.

Revision ID: 97c4a1d0e652
Revises: 6a3f9c1d5e20
"""

from alembic import op
import sqlalchemy as sa


revision = "97c4a1d0e652"
down_revision = "6a3f9c1d5e20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "staff_course_import",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_key", sa.String(64), nullable=False, unique=True),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_year", sa.Integer(), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("position", sa.String(255)),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("provider", sa.String(512)),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("completed_at", sa.Date()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_staff_course_import_source_year", "staff_course_import", ["source_year"])
    op.create_index("ix_staff_course_import_teacher_id", "staff_course_import", ["teacher_id"])


def downgrade():
    op.drop_index("ix_staff_course_import_teacher_id", table_name="staff_course_import")
    op.drop_index("ix_staff_course_import_source_year", table_name="staff_course_import")
    op.drop_table("staff_course_import")
