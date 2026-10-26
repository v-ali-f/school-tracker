"""Instruction versions and classroom safety journal pages.

Revision ID: c2e7b4a9d603
Revises: b7f2c9d4a601
"""

from alembic import op
import sqlalchemy as sa


revision = "c2e7b4a9d603"
down_revision = "b7f2c9d4a601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("safety_officer_assignment", sa.Column("can_manage_instructions", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "safety_instruction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(80), nullable=False, unique=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("briefing_kind", sa.String(80), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("classroom_type", sa.String(80), nullable=True),
        sa.Column("event_kind", sa.String(80), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "safety_instruction_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instruction_id", sa.Integer(), sa.ForeignKey("safety_instruction.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title_snapshot", sa.String(500), nullable=False),
        sa.Column("approved_on", sa.Date(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approval_basis", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(80), nullable=False, unique=True),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("file_mime_type", sa.String(120), nullable=False),
        sa.Column("replaced_version_id", sa.Integer(), sa.ForeignKey("safety_instruction_version.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("instruction_id", "version_number", name="uq_safety_instruction_version_number"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_safety_instruction_period"),
    )
    op.create_index("ix_safety_instruction_version_instruction_id", "safety_instruction_version", ["instruction_id"])
    op.create_table(
        "safety_instruction_access_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("safety_instruction_version.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_safety_instruction_access_event_version_id", "safety_instruction_access_event", ["version_id"])

    op.create_table(
        "safety_journal_page",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_draft_id", sa.String(36), nullable=False, unique=True),
        sa.Column("number", sa.String(50), nullable=False, unique=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("instruction_version_id", sa.Integer(), sa.ForeignKey("safety_instruction_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("instructed_on", sa.Date(), nullable=False),
        sa.Column("group_label", sa.String(255), nullable=False),
        sa.Column("organization_name_snapshot", sa.String(500), nullable=False),
        sa.Column("instructor_name_snapshot", sa.String(255), nullable=False),
        sa.Column("instruction_number_snapshot", sa.String(80), nullable=False),
        sa.Column("instruction_title_snapshot", sa.String(500), nullable=False),
        sa.Column("instruction_summary_snapshot", sa.Text(), nullable=False),
        sa.Column("instruction_file_sha256_snapshot", sa.String(64), nullable=False),
        sa.Column("instruction_version_number_snapshot", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("annulled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("annulled_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("annul_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_safety_journal_page_author_id", "safety_journal_page", ["author_id"])
    op.create_index("ix_safety_journal_page_instruction_version_id", "safety_journal_page", ["instruction_version_id"])
    op.create_index("ix_safety_journal_page_instructed_on", "safety_journal_page", ["instructed_on"])
    op.create_index("ix_safety_journal_page_status", "safety_journal_page", ["status"])

    op.create_table(
        "safety_journal_draft",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("instruction_version_id", sa.Integer(), sa.ForeignKey("safety_instruction_version.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("instructed_on", sa.Date(), nullable=True),
        sa.Column("grade", sa.Integer(), nullable=True),
        sa.Column("class_ids", sa.JSON(), nullable=False),
        sa.Column("selected_child_ids", sa.JSON(), nullable=False),
        sa.Column("removed_child_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("safety_journal_page.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_safety_journal_draft_author_id", "safety_journal_draft", ["author_id"])
    op.create_table(
        "safety_journal_draft_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("safety_journal_draft.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("child.id", ondelete="SET NULL"), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_safety_journal_draft_event_draft_id", "safety_journal_draft_event", ["draft_id"])

    op.create_table(
        "safety_journal_page_class",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("safety_journal_page.id", ondelete="CASCADE"), nullable=False),
        sa.Column("class_id", sa.Integer(), sa.ForeignKey("school_class.id", ondelete="SET NULL"), nullable=True),
        sa.Column("class_name_snapshot", sa.String(30), nullable=False),
        sa.Column("building_id_snapshot", sa.Integer(), nullable=True),
    )
    op.create_index("ix_safety_journal_page_class_page_id", "safety_journal_page_class", ["page_id"])
    op.create_index("ix_safety_journal_page_class_class_id", "safety_journal_page_class", ["class_id"])
    op.create_index("ix_safety_journal_page_class_building_id_snapshot", "safety_journal_page_class", ["building_id_snapshot"])
    op.create_table(
        "safety_journal_participant",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("safety_journal_page.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("child.id", ondelete="SET NULL"), nullable=True),
        sa.Column("full_name_snapshot", sa.String(400), nullable=False),
        sa.Column("birth_date_snapshot", sa.Date(), nullable=False),
        sa.Column("class_name_snapshot", sa.String(30), nullable=False),
        sa.Column("class_id_snapshot", sa.Integer(), nullable=True),
        sa.Column("signature_rule", sa.String(20), nullable=False),
        sa.UniqueConstraint("page_id", "sequence", name="uq_safety_journal_participant_sequence"),
        sa.UniqueConstraint("page_id", "child_id", name="uq_safety_journal_participant_child"),
    )
    op.create_index("ix_safety_journal_participant_page_id", "safety_journal_participant", ["page_id"])
    op.create_table(
        "safety_journal_page_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("safety_journal_page.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("stored_filename", sa.String(80), nullable=False, unique=True),
        sa.Column("pdf_sha256", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("page_id", "version_number", name="uq_safety_journal_page_revision_number"),
    )
    op.create_index("ix_safety_journal_page_revision_page_id", "safety_journal_page_revision", ["page_id"])
    op.create_table(
        "safety_journal_page_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("safety_journal_page.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_safety_journal_page_event_page_id", "safety_journal_page_event", ["page_id"])


def downgrade():
    for name, index in (
        ("safety_journal_page_event", "ix_safety_journal_page_event_page_id"),
        ("safety_journal_page_revision", "ix_safety_journal_page_revision_page_id"),
        ("safety_journal_participant", "ix_safety_journal_participant_page_id"),
        ("safety_journal_page_class", "ix_safety_journal_page_class_building_id_snapshot"),
        ("safety_journal_page_class", "ix_safety_journal_page_class_class_id"),
        ("safety_journal_page_class", "ix_safety_journal_page_class_page_id"),
        ("safety_journal_draft_event", "ix_safety_journal_draft_event_draft_id"),
        ("safety_journal_draft", "ix_safety_journal_draft_author_id"),
        ("safety_journal_page", "ix_safety_journal_page_status"),
        ("safety_journal_page", "ix_safety_journal_page_instructed_on"),
        ("safety_journal_page", "ix_safety_journal_page_instruction_version_id"),
        ("safety_journal_page", "ix_safety_journal_page_author_id"),
        ("safety_instruction_version", "ix_safety_instruction_version_instruction_id"),
        ("safety_instruction_access_event", "ix_safety_instruction_access_event_version_id"),
    ):
        op.drop_index(index, table_name=name)
    for name in (
        "safety_journal_page_event", "safety_journal_page_revision",
        "safety_journal_participant", "safety_journal_page_class",
        "safety_journal_draft_event", "safety_journal_draft",
        "safety_journal_page", "safety_instruction_access_event", "safety_instruction_version", "safety_instruction",
    ):
        op.drop_table(name)
    op.drop_column("safety_officer_assignment", "can_manage_instructions")
