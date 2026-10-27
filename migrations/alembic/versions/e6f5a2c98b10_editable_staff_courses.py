"""Allow corrections and hours on imported staff courses.

Revision ID: e6f5a2c98b10
Revises: 97c4a1d0e652
"""

from alembic import op
import sqlalchemy as sa


revision = "e6f5a2c98b10"
down_revision = "97c4a1d0e652"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("staff_course_import", sa.Column("title_override", sa.String(512), nullable=True))
    op.add_column("staff_course_import", sa.Column("provider_override", sa.String(512), nullable=True))
    op.add_column("staff_course_import", sa.Column("hours", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("staff_course_import", "hours")
    op.drop_column("staff_course_import", "provider_override")
    op.drop_column("staff_course_import", "title_override")
