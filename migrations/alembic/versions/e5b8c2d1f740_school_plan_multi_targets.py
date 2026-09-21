"""School plan multiple responsibles and audience targets.

Revision ID: e5b8c2d1f740
Revises: c6a9e2f4b817
"""

from alembic import op
import sqlalchemy as sa


revision = "e5b8c2d1f740"
down_revision = "c6a9e2f4b817"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "school_plan_event_responsible",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["event_id"], ["school_plan_event.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("event_id", "user_id", name="uq_school_plan_event_responsible"),
    )
    op.create_index("ix_sp_event_responsible_link_event", "school_plan_event_responsible", ["event_id"])
    op.create_index("ix_sp_event_responsible_link_user", "school_plan_event_responsible", ["user_id"])

    op.create_table(
        "school_plan_event_grade",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("grade BETWEEN 1 AND 11", name="ck_school_plan_event_grade_range"),
        sa.ForeignKeyConstraint(["event_id"], ["school_plan_event.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("event_id", "grade", name="uq_school_plan_event_grade"),
    )
    op.create_index("ix_sp_event_grade_link_event", "school_plan_event_grade", ["event_id"])
    op.create_index("ix_sp_event_grade_link_grade", "school_plan_event_grade", ["grade"])

    op.create_table(
        "school_plan_event_class",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["event_id"], ["school_plan_event.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["class_id"], ["school_class.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("event_id", "class_id", name="uq_school_plan_event_class"),
    )
    op.create_index("ix_sp_event_class_link_event", "school_plan_event_class", ["event_id"])
    op.create_index("ix_sp_event_class_link_class", "school_plan_event_class", ["class_id"])


def downgrade():
    op.drop_index("ix_sp_event_class_link_class", table_name="school_plan_event_class")
    op.drop_index("ix_sp_event_class_link_event", table_name="school_plan_event_class")
    op.drop_table("school_plan_event_class")
    op.drop_index("ix_sp_event_grade_link_grade", table_name="school_plan_event_grade")
    op.drop_index("ix_sp_event_grade_link_event", table_name="school_plan_event_grade")
    op.drop_table("school_plan_event_grade")
    op.drop_index("ix_sp_event_responsible_link_user", table_name="school_plan_event_responsible")
    op.drop_index("ix_sp_event_responsible_link_event", table_name="school_plan_event_responsible")
    op.drop_table("school_plan_event_responsible")
