"""Manual department membership and primary-school MCKO diagnostic.

Revision ID: 4c8f2d6a9e10
Revises: e6b9c2a4d713
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "4c8f2d6a9e10"
down_revision = "e6b9c2a4d713"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "department_teacher_membership",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("department.id"), nullable=False),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("department_id", "teacher_id", name="uq_department_teacher_membership"),
        sa.CheckConstraint("mode IN ('INCLUDE','EXCLUDE')", name="ck_department_teacher_membership_mode"),
    )
    op.create_index(
        "ix_department_teacher_membership_department_id",
        "department_teacher_membership",
        ["department_id"],
    )
    op.create_index(
        "ix_department_teacher_membership_teacher_id",
        "department_teacher_membership",
        ["teacher_id"],
    )

    connection = op.get_bind()
    exists = connection.execute(sa.text(
        "SELECT 1 FROM education_activity "
        "WHERE code = :code AND organization_id IS NULL"
    ), {"code": "MCKO_PRIMARY_META"}).first()
    if not exists:
        now = datetime.utcnow()
        connection.execute(sa.text(
            "INSERT INTO education_activity "
            "(code, name, activity_kind, education_level, is_global, "
            "is_tariffable, is_active, created_at, updated_at) "
            "VALUES (:code, :name, 'MODULE', 'NOO', :global, :tariffable, :active, :now, :now)"
        ), {
            "code": "MCKO_PRIMARY_META",
            "name": "Комплексная метапредметная диагностика начальных классов",
            "global": True,
            "tariffable": False,
            "active": True,
            "now": now,
        })


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text(
        "DELETE FROM education_activity WHERE code = :code "
        "AND organization_id IS NULL AND id NOT IN "
        "(SELECT education_activity_id FROM teacher_mcko_result "
        "WHERE education_activity_id IS NOT NULL)"
    ), {"code": "MCKO_PRIMARY_META"})
    op.drop_index(
        "ix_department_teacher_membership_teacher_id",
        table_name="department_teacher_membership",
    )
    op.drop_index(
        "ix_department_teacher_membership_department_id",
        table_name="department_teacher_membership",
    )
    op.drop_table("department_teacher_membership")
