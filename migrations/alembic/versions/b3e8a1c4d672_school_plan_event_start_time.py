"""Add optional start time to school plan events.

Revision ID: b3e8a1c4d672
Revises: a7d0e4f3b962
"""

from alembic import op
import sqlalchemy as sa


revision = "b3e8a1c4d672"
down_revision = "a7d0e4f3b962"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "school_plan_event",
        sa.Column("start_time", sa.Time(), nullable=True),
    )


def downgrade():
    op.drop_column("school_plan_event", "start_time")
