"""Excursion order details, task assignments and trip journal snapshots.

Revision ID: d3f8a5c1e704
Revises: c2e7b4a9d603
"""

from alembic import op
import sqlalchemy as sa


revision = "d3f8a5c1e704"
down_revision = "c2e7b4a9d603"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "safety_trip_order",
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("school_order.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("trip_date", sa.Date(), nullable=False),
        sa.Column("destination", sa.String(500), nullable=False),
        sa.Column("trip_kind", sa.String(120), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "safety_trip_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("safety_trip_order.order_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("task.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("current_page_id", sa.Integer(), sa.ForeignKey("safety_journal_page.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("order_id", "user_id", name="uq_safety_trip_assignment_user"),
    )
    op.create_index("ix_safety_trip_assignment_order_id", "safety_trip_assignment", ["order_id"])
    op.create_index("ix_safety_trip_assignment_user_id", "safety_trip_assignment", ["user_id"])
    op.create_table(
        "safety_trip_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("safety_trip_order.order_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_safety_trip_event_order_id", "safety_trip_event", ["order_id"])
    with op.batch_alter_table("safety_journal_draft") as batch:
        batch.add_column(sa.Column("trip_order_id", sa.Integer(), sa.ForeignKey("safety_trip_order.order_id", name="fk_safety_journal_draft_trip_order_id", ondelete="RESTRICT"), nullable=True))
        batch.add_column(sa.Column("trip_assignment_id", sa.Integer(), sa.ForeignKey("safety_trip_assignment.id", name="fk_safety_journal_draft_trip_assignment_id", ondelete="RESTRICT"), nullable=True))
        batch.add_column(sa.Column("trip_order_revision", sa.Integer(), nullable=True))
        batch.create_index("ix_safety_journal_draft_trip_order_id", ["trip_order_id"])
    with op.batch_alter_table("safety_journal_page") as batch:
        batch.add_column(sa.Column("trip_order_id", sa.Integer(), sa.ForeignKey("safety_trip_order.order_id", name="fk_safety_journal_page_trip_order_id", ondelete="RESTRICT"), nullable=True))
        batch.add_column(sa.Column("trip_assignment_id", sa.Integer(), sa.ForeignKey("safety_trip_assignment.id", name="fk_safety_journal_page_trip_assignment_id", ondelete="RESTRICT"), nullable=True))
        batch.add_column(sa.Column("trip_order_revision", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("trip_snapshot", sa.JSON(), nullable=True))
        batch.create_index("ix_safety_journal_page_trip_order_id", ["trip_order_id"])


def downgrade():
    with op.batch_alter_table("safety_journal_page") as batch:
        batch.drop_index("ix_safety_journal_page_trip_order_id")
        batch.drop_column("trip_snapshot")
        batch.drop_column("trip_order_revision")
        batch.drop_column("trip_assignment_id")
        batch.drop_column("trip_order_id")
    with op.batch_alter_table("safety_journal_draft") as batch:
        batch.drop_index("ix_safety_journal_draft_trip_order_id")
        batch.drop_column("trip_order_revision")
        batch.drop_column("trip_assignment_id")
        batch.drop_column("trip_order_id")
    op.drop_index("ix_safety_trip_event_order_id", table_name="safety_trip_event")
    op.drop_table("safety_trip_event")
    op.drop_index("ix_safety_trip_assignment_user_id", table_name="safety_trip_assignment")
    op.drop_index("ix_safety_trip_assignment_order_id", table_name="safety_trip_assignment")
    op.drop_table("safety_trip_assignment")
    op.drop_table("safety_trip_order")
