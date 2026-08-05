"""Add audit fields for sequential child transfer reversal."""

from alembic import op
import sqlalchemy as sa


revision = "b2d7e4f9a105"
down_revision = "f1a7c3e9b204"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        "child_transfer_history",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column("reversed_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reversed_by", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reversal_reason", sa.Text(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_child_transfer_history_reversed_by_user",
            "user",
            ["reversed_by"],
            ["id"],
        )
        batch_op.create_index(
            "ix_child_transfer_history_reversed_at",
            ["reversed_at"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table(
        "child_transfer_history",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            "ix_child_transfer_history_reversed_at"
        )
        batch_op.drop_constraint(
            "fk_child_transfer_history_reversed_by_user",
            type_="foreignkey",
        )
        batch_op.drop_column("reversal_reason")
        batch_op.drop_column("reversed_by")
        batch_op.drop_column("reversed_at")
