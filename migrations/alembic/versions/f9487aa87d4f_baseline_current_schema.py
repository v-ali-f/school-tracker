"""baseline current schema

Revision ID: f9487aa87d4f
Revises:
Create Date: 2026-07-29
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "f9487aa87d4f"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    schema_path = Path(__file__).with_name(
        "f9487aa87d4f_baseline_current_schema.sql"
    )
    op.get_bind().exec_driver_sql(schema_path.read_text(encoding="utf-8"))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    preparer = bind.dialect.identifier_preparer
    table_names = [
        name
        for name in inspector.get_table_names(schema="public")
        if name != "alembic_version"
    ]
    for table_name in reversed(table_names):
        quoted_name = preparer.quote(table_name)
        bind.exec_driver_sql(
            f"DROP TABLE IF EXISTS public.{quoted_name} CASCADE"
        )
