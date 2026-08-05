"""Add audit fields for sequential child transfer reversal."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "b2d7e4f9a105"
down_revision = "f1a7c3e9b204"
branch_labels = None
depends_on = None

TABLE_NAME = "child_transfer_history"
FK_NAME = "fk_child_transfer_history_reversed_by_user"
INDEX_NAME = "ix_child_transfer_history_reversed_at"


def _column_names(inspector):
    return {c["name"] for c in inspector.get_columns(TABLE_NAME)}


def _fk_names(inspector):
    return {fk.get("name") for fk in inspector.get_foreign_keys(TABLE_NAME)}


def _index_names(inspector):
    return {idx.get("name") for idx in inspector.get_indexes(TABLE_NAME)}


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = _column_names(inspector)

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if "reversed_at" not in columns:
            batch_op.add_column(
                sa.Column("reversed_at", sa.DateTime(), nullable=True)
            )
        if "reversed_by" not in columns:
            batch_op.add_column(
                sa.Column("reversed_by", sa.Integer(), nullable=True)
            )
        if "reversal_reason" not in columns:
            batch_op.add_column(
                sa.Column("reversal_reason", sa.Text(), nullable=True)
            )

    inspector = inspect(bind)
    columns = _column_names(inspector)
    foreign_keys = _fk_names(inspector)
    indexes = _index_names(inspector)

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if "reversed_by" in columns and FK_NAME not in foreign_keys:
            batch_op.create_foreign_key(
                FK_NAME,
                "user",
                ["reversed_by"],
                ["id"],
            )

        if "reversed_at" in columns and INDEX_NAME not in indexes:
            batch_op.create_index(
                INDEX_NAME,
                ["reversed_at"],
                unique=False,
            )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = _column_names(inspector)
    foreign_keys = _fk_names(inspector)
    indexes = _index_names(inspector)

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if INDEX_NAME in indexes:
            batch_op.drop_index(INDEX_NAME)

        if FK_NAME in foreign_keys:
            batch_op.drop_constraint(
                FK_NAME,
                type_="foreignkey",
            )

        if "reversal_reason" in columns:
            batch_op.drop_column("reversal_reason")

        if "reversed_by" in columns:
            batch_op.drop_column("reversed_by")

        if "reversed_at" in columns:
            batch_op.drop_column("reversed_at")