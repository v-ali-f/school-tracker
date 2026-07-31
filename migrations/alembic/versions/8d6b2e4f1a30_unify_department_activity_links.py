"""Backfill the canonical subject-to-department relation.

Revision ID: 8d6b2e4f1a30
Revises: 7c5a1d9e2f40
"""

from alembic import op
import sqlalchemy as sa


revision = "8d6b2e4f1a30"
down_revision = "7c5a1d9e2f40"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    connection.execute(sa.text(
        """
        INSERT INTO education_activity_department (
            education_activity_id,
            department_id,
            is_primary,
            is_active,
            created_at,
            updated_at
        )
        SELECT subject.education_activity_id,
               legacy.department_id,
               FALSE,
               TRUE,
               CURRENT_TIMESTAMP,
               CURRENT_TIMESTAMP
          FROM department_subject AS legacy
          JOIN subject ON subject.id = legacy.subject_id
         WHERE subject.education_activity_id IS NOT NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM education_activity_department AS canonical
                WHERE canonical.education_activity_id = subject.education_activity_id
                  AND canonical.department_id = legacy.department_id
                  AND canonical.valid_from IS NULL
           )
        """
    ))
    connection.execute(sa.text(
        """
        UPDATE education_activity_department AS link
           SET is_primary = (
               link.department_id = chosen.department_id
           )
          FROM (
               SELECT education_activity_id, min(department_id) AS department_id
                 FROM education_activity_department
                WHERE is_active IS TRUE
                  AND valid_from IS NULL
                GROUP BY education_activity_id
          ) AS chosen
         WHERE link.education_activity_id = chosen.education_activity_id
           AND link.valid_from IS NULL
        """
    ))


def downgrade():
    # Canonical links can contain user changes after the migration. Removing
    # them automatically would destroy data, so downgrade keeps the rows.
    pass
