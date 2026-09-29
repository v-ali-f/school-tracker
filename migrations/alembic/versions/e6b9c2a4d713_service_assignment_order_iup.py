"""Add order details and IUP end date to service assignments.

Revision ID: e6b9c2a4d713
Revises: c1d4e8f2a607
"""

from alembic import op
import sqlalchemy as sa


revision = "e6b9c2a4d713"
down_revision = "c1d4e8f2a607"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "service_assignment",
        sa.Column("order_number", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "service_assignment",
        sa.Column("order_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "service_assignment",
        sa.Column("iup_end_date", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_service_assignment_order_number",
        "service_assignment",
        ["order_number"],
    )
    op.create_index(
        "ix_service_assignment_order_date",
        "service_assignment",
        ["order_date"],
    )
    op.create_index(
        "ix_service_assignment_iup_end_date",
        "service_assignment",
        ["iup_end_date"],
    )


def downgrade():
    op.drop_index("ix_service_assignment_iup_end_date", table_name="service_assignment")
    op.drop_index("ix_service_assignment_order_date", table_name="service_assignment")
    op.drop_index("ix_service_assignment_order_number", table_name="service_assignment")
    op.drop_column("service_assignment", "iup_end_date")
    op.drop_column("service_assignment", "order_date")
    op.drop_column("service_assignment", "order_number")
