"""Track the user who created an academic debt.

Revision ID: a9c4e7f1b203
Revises: f8b0c4e6a123
"""

from alembic import op
import sqlalchemy as sa


revision = "a9c4e7f1b203"
down_revision = "f8b0c4e6a123"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("debt") as batch_op:
        batch_op.add_column(
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_debt_created_by_user_id_user",
            "user",
            ["created_by_user_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_debt_created_by_user_id",
            ["created_by_user_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("debt") as batch_op:
        batch_op.drop_index("ix_debt_created_by_user_id")
        batch_op.drop_constraint(
            "fk_debt_created_by_user_id_user",
            type_="foreignkey",
        )
        batch_op.drop_column("created_by_user_id")
