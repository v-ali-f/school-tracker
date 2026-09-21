"""School plan staff groups and editor access.

Revision ID: f6c9d3e2a851
Revises: e5b8c2d1f740
"""

from alembic import op
import sqlalchemy as sa


revision = "f6c9d3e2a851"
down_revision = "e5b8c2d1f740"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "school_plan_event_group",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("group_type", sa.String(length=30), nullable=False),
        sa.Column("group_key", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "purpose IN ('audience', 'responsible')",
            name="ck_school_plan_event_group_purpose",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["school_plan_event.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "event_id",
            "purpose",
            "group_type",
            "group_key",
            name="uq_school_plan_event_group",
        ),
    )
    op.create_index("ix_sp_event_group_link_event", "school_plan_event_group", ["event_id"])
    op.create_index(
        "ix_sp_event_group_purpose_type",
        "school_plan_event_group",
        ["purpose", "group_type"],
    )

    op.create_table(
        "school_plan_editor_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["user.id"]),
        sa.UniqueConstraint("user_id", name="uq_school_plan_editor_access_user"),
    )
    op.create_index("ix_sp_editor_access_user", "school_plan_editor_access", ["user_id"])


def downgrade():
    op.drop_index("ix_sp_editor_access_user", table_name="school_plan_editor_access")
    op.drop_table("school_plan_editor_access")
    op.drop_index("ix_sp_event_group_purpose_type", table_name="school_plan_event_group")
    op.drop_index("ix_sp_event_group_link_event", table_name="school_plan_event_group")
    op.drop_table("school_plan_event_group")
