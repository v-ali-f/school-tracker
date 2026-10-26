"""Safety passport registry and immutable revision history.

Revision ID: b7f2c9d4a601
Revises: e6b9c2a4d713
"""

from alembic import op
import sqlalchemy as sa


revision = "b7f2c9d4a601"
down_revision = "e6b9c2a4d713"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("school_classroom") as batch:
        batch.add_column(sa.Column("room_type", sa.String(80), nullable=True))
        batch.add_column(sa.Column("floor", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("area", sa.Numeric(8, 2), nullable=True))
        batch.create_check_constraint("ck_school_classroom_area_positive", "area IS NULL OR area > 0")

    op.create_table(
        "safety_officer_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("assigned_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True),
        sa.CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_safety_officer_period"),
    )
    op.create_index("ix_safety_officer_assignment_user_id", "safety_officer_assignment", ["user_id"])

    op.create_table(
        "safety_passport",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("classroom_id", sa.Integer(), sa.ForeignKey("school_classroom.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("template_code", sa.String(50), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_revision_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "safety_passport_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("passport_id", sa.Integer(), sa.ForeignKey("safety_passport.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("passport_id", "number", name="uq_safety_passport_revision_number"),
    )
    op.create_index("ix_safety_passport_revision_passport_id", "safety_passport_revision", ["passport_id"])
    op.create_table(
        "safety_passport_review",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision_id", sa.Integer(), sa.ForeignKey("safety_passport_revision.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_safety_passport_review_revision_id", "safety_passport_review", ["revision_id"])
    op.create_table(
        "safety_passport_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("passport_id", sa.Integer(), sa.ForeignKey("safety_passport.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(80), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_safety_passport_document_passport_id", "safety_passport_document", ["passport_id"])
    op.execute(sa.text("""
        INSERT INTO safety_passport
            (classroom_id, template_code, template_version, status,
             current_revision_number, created_at, updated_at)
        SELECT room.id,
               CASE WHEN lower(COALESCE(room.room_type, '')) LIKE '%начальн%'
                    THEN 'primary' ELSE 'general' END,
               1, 'not_started', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM school_classroom AS room
        WHERE room.teacher_user_id IS NOT NULL
           OR EXISTS (
               SELECT 1 FROM school_classroom_teacher AS link
               WHERE link.classroom_id = room.id
           )
    """))


def downgrade():
    op.drop_index("ix_safety_passport_document_passport_id", table_name="safety_passport_document")
    op.drop_table("safety_passport_document")
    op.drop_index("ix_safety_passport_review_revision_id", table_name="safety_passport_review")
    op.drop_table("safety_passport_review")
    op.drop_index("ix_safety_passport_revision_passport_id", table_name="safety_passport_revision")
    op.drop_table("safety_passport_revision")
    op.drop_table("safety_passport")
    op.drop_index("ix_safety_officer_assignment_user_id", table_name="safety_officer_assignment")
    op.drop_table("safety_officer_assignment")
    with op.batch_alter_table("school_classroom") as batch:
        batch.drop_constraint("ck_school_classroom_area_positive", type_="check")
        batch.drop_column("area")
        batch.drop_column("floor")
        batch.drop_column("room_type")
