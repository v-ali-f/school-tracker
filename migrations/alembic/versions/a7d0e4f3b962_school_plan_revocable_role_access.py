"""Make role-based school plan access revocable.

Revision ID: a7d0e4f3b962
Revises: f6c9d3e2a851
"""

from alembic import op
import sqlalchemy as sa


revision = "a7d0e4f3b962"
down_revision = "f6c9d3e2a851"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "school_plan_editor_access",
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade():
    op.drop_column("school_plan_editor_access", "is_enabled")
