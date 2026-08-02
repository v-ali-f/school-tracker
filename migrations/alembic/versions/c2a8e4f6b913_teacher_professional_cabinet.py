"""Add teacher attestation records.

Revision ID: c2a8e4f6b913
Revises: b7e4d9a1c632
"""

from alembic import op
import sqlalchemy as sa


revision = "c2a8e4f6b913"
down_revision = "b7e4d9a1c632"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table("teacher_attestation"):
        return
    op.create_table(
        "teacher_attestation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("position_title", sa.String(length=255), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("order_number", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["teacher_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_teacher_attestation_teacher_id",
        "teacher_attestation",
        ["teacher_id"],
        unique=False,
    )


def downgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("teacher_attestation"):
        return
    op.drop_index(
        "ix_teacher_attestation_teacher_id",
        table_name="teacher_attestation",
    )
    op.drop_table("teacher_attestation")
