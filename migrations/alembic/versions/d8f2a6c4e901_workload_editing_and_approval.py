"""Add editing locks for groups and workload approval.

Revision ID: d8f2a6c4e901
Revises: c4f8a2d6e913
"""

from alembic import op
import sqlalchemy as sa


revision = "d8f2a6c4e901"
down_revision = "c4f8a2d6e913"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tariff_version", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "groups_editing_status",
            sa.String(length=30),
            server_default="EDITING",
            nullable=False,
        ))
        batch_op.add_column(sa.Column(
            "workload_approval_status",
            sa.String(length=30),
            server_default="EDITING",
            nullable=False,
        ))
        batch_op.add_column(sa.Column(
            "workload_review_comment",
            sa.String(length=500),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            "workload_submitted_at",
            sa.DateTime(),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            "workload_reviewed_at",
            sa.DateTime(),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            "workload_reviewed_by_user_id",
            sa.Integer(),
            nullable=True,
        ))
        batch_op.create_foreign_key(
            "fk_tariff_version_workload_reviewed_by_user_id_user",
            "user",
            ["workload_reviewed_by_user_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_tariff_version_groups_editing_status",
            "groups_editing_status IN ('EDITING','SAVED')",
        )
        batch_op.create_check_constraint(
            "ck_tariff_version_workload_approval_status",
            "workload_approval_status IN ("
            "'EDITING','SAVED','PENDING_APPROVAL','APPROVED',"
            "'CHANGES_REQUESTED'"
            ")",
        )
        batch_op.create_index(
            batch_op.f("ix_tariff_version_groups_editing_status"),
            ["groups_editing_status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_tariff_version_workload_approval_status"),
            ["workload_approval_status"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("tariff_version", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_tariff_version_workload_approval_status")
        )
        batch_op.drop_index(
            batch_op.f("ix_tariff_version_groups_editing_status")
        )
        batch_op.drop_constraint(
            "ck_tariff_version_workload_approval_status",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_tariff_version_groups_editing_status",
            type_="check",
        )
        batch_op.drop_constraint(
            "fk_tariff_version_workload_reviewed_by_user_id_user",
            type_="foreignkey",
        )
        batch_op.drop_column("workload_reviewed_by_user_id")
        batch_op.drop_column("workload_reviewed_at")
        batch_op.drop_column("workload_submitted_at")
        batch_op.drop_column("workload_review_comment")
        batch_op.drop_column("workload_approval_status")
        batch_op.drop_column("groups_editing_status")
