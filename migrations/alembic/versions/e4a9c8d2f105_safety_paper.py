"""Physical journal review, filing and scan versions.

Revision ID: e4a9c8d2f105
Revises: d3f8a5c1e704
"""

from alembic import op
import sqlalchemy as sa


revision = "e4a9c8d2f105"
down_revision = "d3f8a5c1e704"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "safety_journal_paper_record",
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("safety_journal_page.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("check_note", sa.Text(), nullable=True),
        sa.Column("issue_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issue_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("issue_note", sa.Text(), nullable=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filed_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("binder_ref", sa.String(255), nullable=True),
        sa.Column("sheet_ref", sa.String(80), nullable=True),
    )
    op.create_table(
        "safety_journal_paper_scan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("safety_journal_page.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("stored_filename", sa.String(80), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(50), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("page_id", "version_number", name="uq_safety_journal_paper_scan_version"),
    )
    op.create_index("ix_safety_journal_paper_scan_page_id", "safety_journal_paper_scan", ["page_id"])


def downgrade():
    op.drop_index("ix_safety_journal_paper_scan_page_id", table_name="safety_journal_paper_scan")
    op.drop_table("safety_journal_paper_scan")
    op.drop_table("safety_journal_paper_record")
