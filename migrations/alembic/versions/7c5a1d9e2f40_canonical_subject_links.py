"""Add canonical education activity links to legacy subject consumers.

Revision ID: 7c5a1d9e2f40
Revises: 6b4f2a9c1d80
"""

from alembic import op
import sqlalchemy as sa


revision = "7c5a1d9e2f40"
down_revision = "6b4f2a9c1d80"
branch_labels = None
depends_on = None


SUBJECT_LINK_TABLES = (
    "department_subject",
    "teacher_load",
    "teacher_mcko_result",
    "debt",
    "control_work",
    "olympiad_import_session",
    "olympiad_result",
    "olympiad_subject_mapping",
)


def _add_activity_link(table_name):
    op.add_column(
        table_name,
        sa.Column("education_activity_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        f"ix_{table_name}_education_activity_id",
        table_name,
        ["education_activity_id"],
        unique=False,
    )
    op.create_foreign_key(
        f"fk_{table_name}_education_activity_id",
        table_name,
        "education_activity",
        ["education_activity_id"],
        ["id"],
    )


def upgrade():
    for table_name in SUBJECT_LINK_TABLES:
        _add_activity_link(table_name)

    _add_activity_link("diagnostic_session")

    connection = op.get_bind()
    for table_name in SUBJECT_LINK_TABLES:
        connection.execute(sa.text(
            f"""
            UPDATE {table_name} AS target
               SET education_activity_id = subject.education_activity_id
              FROM subject
             WHERE target.subject_id = subject.id
               AND subject.education_activity_id IS NOT NULL
               AND target.education_activity_id IS NULL
            """
        ))

    connection.execute(sa.text(
        """
        UPDATE diagnostic_session AS target
           SET education_activity_id = activity.id
          FROM education_activity AS activity
         WHERE target.education_activity_id IS NULL
           AND target.subject IS NOT NULL
           AND lower(trim(target.subject)) = lower(trim(activity.name))
           AND activity.activity_kind = 'SUBJECT'
        """
    ))


def downgrade():
    for table_name in reversed((*SUBJECT_LINK_TABLES, "diagnostic_session")):
        op.drop_constraint(
            f"fk_{table_name}_education_activity_id",
            table_name,
            type_="foreignkey",
        )
        op.drop_index(
            f"ix_{table_name}_education_activity_id",
            table_name=table_name,
        )
        op.drop_column(table_name, "education_activity_id")
