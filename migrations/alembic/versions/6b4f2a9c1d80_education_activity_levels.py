"""Add multiple education levels to the unified activity catalog.

Revision ID: 6b4f2a9c1d80
Revises: 91f2c7d4a8b6
"""

from alembic import op
import sqlalchemy as sa


revision = "6b4f2a9c1d80"
down_revision = "91f2c7d4a8b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "education_activity_level",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("education_activity_id", sa.Integer(), nullable=False),
        sa.Column("education_level", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "education_level IN ('NOO','OOO','SOO','DO')",
            name="ck_education_activity_level_code",
        ),
        sa.ForeignKeyConstraint(
            ["education_activity_id"],
            ["education_activity.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "education_activity_id",
            "education_level",
            name="uq_education_activity_level",
        ),
    )
    op.create_index(
        "ix_education_activity_level_education_activity_id",
        "education_activity_level",
        ["education_activity_id"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_level_education_level",
        "education_activity_level",
        ["education_level"],
        unique=False,
    )

    connection = op.get_bind()
    connection.execute(sa.text(
        """
        INSERT INTO education_activity_level (
            education_activity_id,
            education_level
        )
        SELECT id, education_level
          FROM education_activity
         WHERE education_level IN ('NOO', 'OOO', 'SOO', 'DO')
        """
    ))


def downgrade():
    op.drop_index(
        "ix_education_activity_level_education_level",
        table_name="education_activity_level",
    )
    op.drop_index(
        "ix_education_activity_level_education_activity_id",
        table_name="education_activity_level",
    )
    op.drop_table("education_activity_level")
