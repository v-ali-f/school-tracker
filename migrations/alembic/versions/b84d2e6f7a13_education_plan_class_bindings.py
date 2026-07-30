"""education plan class and student bindings

Revision ID: b84d2e6f7a13
Revises: f53c9d7a2e84
Create Date: 2026-07-30 18:30:00

"""
from alembic import op
import sqlalchemy as sa


revision = "b84d2e6f7a13"
down_revision = "f53c9d7a2e84"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "education_plan_binding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("education_plan_id", sa.Integer(), nullable=False),
        sa.Column(
            "population_snapshot_class_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "binding_mode",
            sa.String(length=20),
            server_default="STUDENTS",
            nullable=False,
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "binding_mode IN ('CLASS','STUDENTS')",
            name="ck_education_plan_binding_mode",
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_education_plan_binding_revision",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["education_plan_id"],
            ["education_plan.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["population_snapshot_class_id"],
            ["population_snapshot_class.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "education_plan_id",
            "population_snapshot_class_id",
            name="uq_education_plan_binding_plan_class",
        ),
    )
    with op.batch_alter_table(
        "education_plan_binding",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            "ix_education_plan_binding_education_plan_id",
            ["education_plan_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_education_plan_binding_population_snapshot_class_id",
            ["population_snapshot_class_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_education_plan_binding_class_plan",
            ["population_snapshot_class_id", "education_plan_id"],
            unique=False,
        )

    op.create_table(
        "education_plan_binding_member",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "education_plan_binding_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "snapshot_enrollment_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["education_plan_binding_id"],
            ["education_plan_binding.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_enrollment_id"],
            ["population_snapshot_enrollment.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "education_plan_binding_id",
            "snapshot_enrollment_id",
            name="uq_education_plan_binding_member",
        ),
    )
    with op.batch_alter_table(
        "education_plan_binding_member",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            "ix_education_plan_binding_member_education_plan_binding_id",
            ["education_plan_binding_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_education_plan_binding_member_snapshot_enrollment_id",
            ["snapshot_enrollment_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_education_plan_binding_member_enrollment",
            ["snapshot_enrollment_id", "education_plan_binding_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table(
        "education_plan_binding_member",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            "ix_education_plan_binding_member_enrollment"
        )
        batch_op.drop_index(
            "ix_education_plan_binding_member_snapshot_enrollment_id"
        )
        batch_op.drop_index(
            "ix_education_plan_binding_member_education_plan_binding_id"
        )
    op.drop_table("education_plan_binding_member")

    with op.batch_alter_table(
        "education_plan_binding",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            "ix_education_plan_binding_class_plan"
        )
        batch_op.drop_index(
            "ix_education_plan_binding_population_snapshot_class_id"
        )
        batch_op.drop_index(
            "ix_education_plan_binding_education_plan_id"
        )
    op.drop_table("education_plan_binding")
