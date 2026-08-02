"""Academic year rollover integrity guards.

Revision ID: d6f8a2c4e901
Revises: c2a8e4f6b913
"""

from alembic import op
import sqlalchemy as sa


revision = "d6f8a2c4e901"
down_revision = "c2a8e4f6b913"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    duplicate_classes = connection.execute(sa.text("""
        SELECT academic_year_id, upper(replace(replace(name, ' ', ''), '-', ''))
        FROM school_class
        GROUP BY academic_year_id,
                 upper(replace(replace(name, ' ', ''), '-', ''))
        HAVING count(*) > 1
        LIMIT 1
    """)).first()
    if duplicate_classes:
        raise RuntimeError(
            "Найдены одинаковые названия классов в одном учебном году. "
            "Устраните дубли перед миграцией."
        )
    duplicate_enrollments = connection.execute(sa.text("""
        SELECT child_id, academic_year_id
        FROM child_enrollment
        WHERE ended_at IS NULL
        GROUP BY child_id, academic_year_id
        HAVING count(*) > 1
        LIMIT 1
    """)).first()
    if duplicate_enrollments:
        raise RuntimeError(
            "У ученика найдено несколько активных зачислений в одном "
            "учебном году. Устраните дубли перед миграцией."
        )

    with op.batch_alter_table("school_class") as batch_op:
        batch_op.drop_constraint(
            "uq_school_class_year_building_name",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_school_class_year_name",
            ["academic_year_id", "name"],
        )

    op.create_index(
        "uq_child_enrollment_active_year",
        "child_enrollment",
        ["child_id", "academic_year_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )


def downgrade():
    op.drop_index(
        "uq_child_enrollment_active_year",
        table_name="child_enrollment",
    )
    with op.batch_alter_table("school_class") as batch_op:
        batch_op.drop_constraint(
            "uq_school_class_year_name",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_school_class_year_building_name",
            ["academic_year_id", "building_id", "name"],
        )
