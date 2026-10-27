"""Quality of education import snapshots.

Revision ID: 6a3f9c1d5e20
Revises: 4c8f2d6a9e10
"""

from alembic import op
import sqlalchemy as sa


revision = "6a3f9c1d5e20"
down_revision = "4c8f2d6a9e10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quality_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("academic_year_id", sa.Integer(), sa.ForeignKey("academic_year.id"), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("imported_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_quality_snapshot_academic_year_id", "quality_snapshot", ["academic_year_id"])
    op.create_index("ix_quality_snapshot_source_type", "quality_snapshot", ["source_type"])


def downgrade():
    op.drop_index("ix_quality_snapshot_source_type", table_name="quality_snapshot")
    op.drop_index("ix_quality_snapshot_academic_year_id", table_name="quality_snapshot")
    op.drop_table("quality_snapshot")
