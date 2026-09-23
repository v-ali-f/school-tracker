"""Add lesson observation registry.

Revision ID: c1d4e8f2a607
Revises: b3e8a1c4d672
"""

from alembic import op
import sqlalchemy as sa


revision = "c1d4e8f2a607"
down_revision = "b3e8a1c4d672"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "lesson_visit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("observer_id", sa.Integer(), nullable=False),
        sa.Column("academic_year_id", sa.Integer(), nullable=True),
        sa.Column("workload_assignment_id", sa.Integer(), nullable=True),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("parallel", sa.SmallInteger(), nullable=True),
        sa.Column("class_name", sa.String(length=120), nullable=False),
        sa.Column("subject_name", sa.String(length=255), nullable=False),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("strengths", sa.Text(), nullable=False),
        sa.Column("growth_areas", sa.Text(), nullable=False),
        sa.Column("repeat_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "parallel IS NULL OR (parallel >= 1 AND parallel <= 11)",
            name="ck_lesson_visit_parallel",
        ),
        sa.ForeignKeyConstraint(["teacher_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["observer_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["academic_year_id"], ["academic_year.id"]),
        sa.ForeignKeyConstraint(
            ["workload_assignment_id"],
            ["workload_assignment.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_lesson_visit_teacher_id", "lesson_visit", ["teacher_id"])
    op.create_index("ix_lesson_visit_observer_id", "lesson_visit", ["observer_id"])
    op.create_index("ix_lesson_visit_academic_year_id", "lesson_visit", ["academic_year_id"])
    op.create_index("ix_lesson_visit_workload_assignment_id", "lesson_visit", ["workload_assignment_id"])
    op.create_index("ix_lesson_visit_visit_date", "lesson_visit", ["visit_date"])
    op.create_index("ix_lesson_visit_parallel", "lesson_visit", ["parallel"])
    op.create_index("ix_lesson_visit_repeat_required", "lesson_visit", ["repeat_required"])
    op.create_index("ix_lesson_visit_teacher_date", "lesson_visit", ["teacher_id", "visit_date"])


def downgrade():
    op.drop_table("lesson_visit")
