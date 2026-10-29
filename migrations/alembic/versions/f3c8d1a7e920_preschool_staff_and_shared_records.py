"""Preschool staffing, access, achievements, and shared professional fields.

Revision ID: f3c8d1a7e920
Revises: d8a2e4b7c019
"""

from alembic import op
import sqlalchemy as sa


revision = "f3c8d1a7e920"
down_revision = "d8a2e4b7c019"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table):
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _add_column(table, column):
    if column.name not in _columns(table):
        op.add_column(table, column)


def _create_table(name, *columns):
    if name not in _tables():
        op.create_table(name, *columns)


def upgrade():
    _create_table(
        "preschool_building_staff",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
        sa.Column("position", sa.String(40), nullable=False),
        sa.Column("start_date", sa.Date()), sa.Column("end_date", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("assigned_by_user_id", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("building_id", "user_id", "position", name="uq_preschool_building_staff"),
    )
    _create_table(
        "preschool_group_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("preschool_group.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
        sa.Column("position", sa.String(40), nullable=False),
        sa.Column("academic_year_id", sa.Integer(), sa.ForeignKey("academic_year.id")),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id")),
        sa.Column("start_date", sa.Date()), sa.Column("end_date", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("assigned_by_user_id", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("group_id", "user_id", "position", name="uq_preschool_group_staff"),
    )
    _create_table(
        "preschool_staff_change",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id")),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("preschool_group.id")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("position", sa.String(40), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    _create_table(
        "preschool_achievement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("preschool_child.id")),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("preschool_group.id")),
        sa.Column("event_name", sa.String(255), nullable=False),
        sa.Column("level", sa.String(120)), sa.Column("organizer", sa.String(255)),
        sa.Column("event_date", sa.Date()), sa.Column("result", sa.String(255)),
        sa.Column("award", sa.String(255)), sa.Column("document", sa.String(255)),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    _create_table(
        "preschool_profile_change",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("old_values", sa.JSON(), nullable=False),
        sa.Column("new_values", sa.JSON(), nullable=False),
    )
    _create_table(
        "preschool_dashboard_setting",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("warning_months", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    _create_table(
        "preschool_responsibility",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False, unique=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), index=True),
        sa.Column("assigned_by_user_id", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    _create_table(
        "preschool_responsibility_change",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False, index=True),
        sa.Column("previous_user_id", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("new_user_id", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for table, columns in {
        "preschool_child_movement": [
            sa.Column("from_status", sa.String(50)), sa.Column("to_status", sa.String(50)),
            sa.Column("created_by_user_id", sa.Integer()), sa.Column("reversed_at", sa.DateTime()),
            sa.Column("reversed_by_user_id", sa.Integer()),
        ],
        "teacher_mcko_result": [sa.Column("diagnostic_title", sa.String(255))],
        "teacher_course": [
            sa.Column("document_title", sa.String(255)), sa.Column("document_number", sa.String(120)),
            sa.Column("entry_source", sa.String(24), server_default="LEGACY"),
            sa.Column("created_by_user_id", sa.Integer()), sa.Column("updated_by_user_id", sa.Integer()),
            sa.Column("updated_at", sa.DateTime()),
        ],
    }.items():
        if table in _tables():
            for column in columns:
                _add_column(table, column)


def downgrade():
    for table, names in {
        "teacher_course": ("updated_at", "updated_by_user_id", "created_by_user_id", "entry_source", "document_number", "document_title"),
        "teacher_mcko_result": ("diagnostic_title",),
        "preschool_child_movement": ("reversed_by_user_id", "reversed_at", "created_by_user_id", "to_status", "from_status"),
    }.items():
        if table in _tables():
            for name in names:
                if name in _columns(table):
                    op.drop_column(table, name)
    for table in (
        "preschool_responsibility_change", "preschool_responsibility", "preschool_dashboard_setting",
        "preschool_profile_change", "preschool_achievement", "preschool_staff_change",
        "preschool_group_assignment", "preschool_building_staff",
    ):
        if table in _tables():
            op.drop_table(table)
