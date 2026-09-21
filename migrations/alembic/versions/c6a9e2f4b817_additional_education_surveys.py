"""Additional education survey forms.

Revision ID: c6a9e2f4b817
Revises: a8d4e6f1b230
"""

from alembic import op
import sqlalchemy as sa


revision = "c6a9e2f4b817"
down_revision = "a8d4e6f1b230"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "additional_education_survey",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("public_token", sa.String(length=64), nullable=False),
        sa.Column("short_code", sa.String(length=40), nullable=True),
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.UniqueConstraint(
            "public_token",
            name="uq_additional_education_survey_public_token",
        ),
        sa.UniqueConstraint(
            "short_code",
            name="uq_additional_education_survey_short_code",
        ),
    )
    op.create_index(
        "ix_additional_education_survey_public_token",
        "additional_education_survey",
        ["public_token"],
        unique=True,
    )
    op.create_index(
        "ix_additional_education_survey_short_code",
        "additional_education_survey",
        ["short_code"],
        unique=True,
    )
    op.create_index(
        "ix_additional_education_survey_is_published",
        "additional_education_survey",
        ["is_published"],
    )
    op.create_index(
        "ix_additional_education_survey_created_by_user_id",
        "additional_education_survey",
        ["created_by_user_id"],
    )

    op.create_table(
        "additional_education_survey_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("survey_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["survey_id"],
            ["additional_education_survey.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "survey_id",
            "user_id",
            name="uq_add_edu_survey_access_survey_user",
        ),
    )
    op.create_index(
        "ix_additional_education_survey_access_survey_id",
        "additional_education_survey_access",
        ["survey_id"],
    )
    op.create_index(
        "ix_additional_education_survey_access_user_id",
        "additional_education_survey_access",
        ["user_id"],
    )
    op.create_index(
        "ix_additional_education_survey_access_granted_by_user_id",
        "additional_education_survey_access",
        ["granted_by_user_id"],
    )

    op.create_table(
        "additional_education_survey_question",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("survey_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=500), nullable=False),
        sa.Column("help_text", sa.String(length=500), nullable=True),
        sa.Column(
            "field_type",
            sa.String(length=30),
            nullable=False,
            server_default="short_text",
        ),
        sa.Column("options_json", sa.Text(), nullable=True),
        sa.Column(
            "is_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["survey_id"],
            ["additional_education_survey.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_additional_education_survey_question_survey_id",
        "additional_education_survey_question",
        ["survey_id"],
    )

    op.create_table(
        "additional_education_survey_submission",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("survey_id", sa.Integer(), nullable=False),
        sa.Column("receipt_token", sa.String(length=64), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["survey_id"],
            ["additional_education_survey.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "receipt_token",
            name="uq_additional_education_survey_submission_receipt_token",
        ),
    )
    op.create_index(
        "ix_additional_education_survey_submission_survey_id",
        "additional_education_survey_submission",
        ["survey_id"],
    )
    op.create_index(
        "ix_additional_education_survey_submission_receipt_token",
        "additional_education_survey_submission",
        ["receipt_token"],
        unique=True,
    )
    op.create_index(
        "ix_additional_education_survey_submission_submitted_at",
        "additional_education_survey_submission",
        ["submitted_at"],
    )

    op.create_table(
        "additional_education_survey_answer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["additional_education_survey_submission.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["additional_education_survey_question.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "submission_id",
            "question_id",
            name="uq_add_edu_answer_submission_question",
        ),
    )
    op.create_index(
        "ix_additional_education_survey_answer_submission_id",
        "additional_education_survey_answer",
        ["submission_id"],
    )
    op.create_index(
        "ix_additional_education_survey_answer_question_id",
        "additional_education_survey_answer",
        ["question_id"],
    )

    op.create_table(
        "additional_education_survey_attachment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("answer_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["additional_education_survey_answer.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_additional_education_survey_attachment_answer_id",
        "additional_education_survey_attachment",
        ["answer_id"],
    )


def downgrade():
    op.drop_index(
        "ix_additional_education_survey_attachment_answer_id",
        table_name="additional_education_survey_attachment",
    )
    op.drop_table("additional_education_survey_attachment")
    op.drop_index(
        "ix_additional_education_survey_answer_question_id",
        table_name="additional_education_survey_answer",
    )
    op.drop_index(
        "ix_additional_education_survey_answer_submission_id",
        table_name="additional_education_survey_answer",
    )
    op.drop_table("additional_education_survey_answer")
    op.drop_index(
        "ix_additional_education_survey_submission_submitted_at",
        table_name="additional_education_survey_submission",
    )
    op.drop_index(
        "ix_additional_education_survey_submission_receipt_token",
        table_name="additional_education_survey_submission",
    )
    op.drop_index(
        "ix_additional_education_survey_submission_survey_id",
        table_name="additional_education_survey_submission",
    )
    op.drop_table("additional_education_survey_submission")
    op.drop_index(
        "ix_additional_education_survey_question_survey_id",
        table_name="additional_education_survey_question",
    )
    op.drop_table("additional_education_survey_question")
    op.drop_index(
        "ix_additional_education_survey_access_granted_by_user_id",
        table_name="additional_education_survey_access",
    )
    op.drop_index(
        "ix_additional_education_survey_access_user_id",
        table_name="additional_education_survey_access",
    )
    op.drop_index(
        "ix_additional_education_survey_access_survey_id",
        table_name="additional_education_survey_access",
    )
    op.drop_table("additional_education_survey_access")
    op.drop_index(
        "ix_additional_education_survey_created_by_user_id",
        table_name="additional_education_survey",
    )
    op.drop_index(
        "ix_additional_education_survey_is_published",
        table_name="additional_education_survey",
    )
    op.drop_index(
        "ix_additional_education_survey_short_code",
        table_name="additional_education_survey",
    )
    op.drop_index(
        "ix_additional_education_survey_public_token",
        table_name="additional_education_survey",
    )
    op.drop_table("additional_education_survey")
