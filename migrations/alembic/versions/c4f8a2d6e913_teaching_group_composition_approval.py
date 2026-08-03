"""Store class teacher approvals for teaching group compositions.

Revision ID: c4f8a2d6e913
Revises: e3b7c1d9a524
"""

from alembic import op
import sqlalchemy as sa


revision = "c4f8a2d6e913"
down_revision = "e3b7c1d9a524"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teaching_group_composition_approval",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tariff_version_id", sa.Integer(), nullable=False),
        sa.Column("education_plan_line_id", sa.Integer(), nullable=False),
        sa.Column(
            "population_snapshot_class_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["education_plan_line_id"],
            ["education_plan_line.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["population_snapshot_class_id"],
            ["population_snapshot_class.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tariff_version_id"],
            ["tariff_version.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tariff_version_id",
            "education_plan_line_id",
            "population_snapshot_class_id",
            name="uq_teaching_group_composition_approval_cell",
        ),
    )
    with op.batch_alter_table(
        "teaching_group_composition_approval",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            batch_op.f(
                "ix_teaching_group_composition_approval_"
                "approved_by_user_id"
            ),
            ["approved_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f(
                "ix_teaching_group_composition_approval_"
                "education_plan_line_id"
            ),
            ["education_plan_line_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f(
                "ix_teaching_group_composition_approval_"
                "population_snapshot_class_id"
            ),
            ["population_snapshot_class_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f(
                "ix_teaching_group_composition_approval_"
                "tariff_version_id"
            ),
            ["tariff_version_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_teaching_group_composition_approval_version_class",
            ["tariff_version_id", "population_snapshot_class_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table(
        "teaching_group_composition_approval",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            "ix_teaching_group_composition_approval_version_class"
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_teaching_group_composition_approval_"
                "tariff_version_id"
            )
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_teaching_group_composition_approval_"
                "population_snapshot_class_id"
            )
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_teaching_group_composition_approval_"
                "education_plan_line_id"
            )
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_teaching_group_composition_approval_"
                "approved_by_user_id"
            )
        )
    op.drop_table("teaching_group_composition_approval")
