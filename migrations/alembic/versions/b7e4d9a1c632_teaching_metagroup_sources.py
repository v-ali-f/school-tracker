"""Store source groups of teaching metagroups.

Revision ID: b7e4d9a1c632
Revises: a1f8d4c6b209
"""

from alembic import op
import sqlalchemy as sa


revision = "b7e4d9a1c632"
down_revision = "a1f8d4c6b209"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teaching_metagroup_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metagroup_id", sa.Integer(), nullable=False),
        sa.Column("source_group_id", sa.Integer(), nullable=False),
        sa.Column(
            "sort_order",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.CheckConstraint(
            "metagroup_id <> source_group_id",
            name="ck_teaching_metagroup_distinct_source",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_teaching_metagroup_source_order",
        ),
        sa.ForeignKeyConstraint(
            ["metagroup_id"],
            ["teaching_group.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_group_id"],
            ["teaching_group.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "metagroup_id",
            "source_group_id",
            name="uq_teaching_metagroup_source",
        ),
        sa.UniqueConstraint(
            "source_group_id",
            name="uq_teaching_metagroup_single_membership",
        ),
    )
    with op.batch_alter_table(
        "teaching_metagroup_source",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            batch_op.f(
                "ix_teaching_metagroup_source_metagroup_id"
            ),
            ["metagroup_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f(
                "ix_teaching_metagroup_source_source_group_id"
            ),
            ["source_group_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table(
        "teaching_metagroup_source",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f(
                "ix_teaching_metagroup_source_source_group_id"
            )
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_teaching_metagroup_source_metagroup_id"
            )
        )
    op.drop_table("teaching_metagroup_source")
