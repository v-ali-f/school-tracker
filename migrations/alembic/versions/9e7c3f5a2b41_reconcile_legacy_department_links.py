"""Reconcile the legacy department adapter from canonical activity links.

Revision ID: 9e7c3f5a2b41
Revises: 8d6b2e4f1a30
"""

from alembic import op
import sqlalchemy as sa


revision = "9e7c3f5a2b41"
down_revision = "8d6b2e4f1a30"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    connection.execute(sa.text(
        """
        INSERT INTO department_subject (
            department_id,
            subject_id,
            education_activity_id
        )
        SELECT canonical.department_id,
               subject.id,
               canonical.education_activity_id
          FROM education_activity_department AS canonical
          JOIN subject
            ON subject.education_activity_id = canonical.education_activity_id
         WHERE canonical.is_active IS TRUE
           AND canonical.valid_from IS NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM department_subject AS legacy
                WHERE legacy.department_id = canonical.department_id
                  AND legacy.subject_id = subject.id
           )
        """
    ))
    connection.execute(sa.text(
        """
        UPDATE department_subject AS legacy
           SET education_activity_id = subject.education_activity_id
          FROM subject
         WHERE legacy.subject_id = subject.id
           AND subject.education_activity_id IS NOT NULL
        """
    ))
    connection.execute(sa.text(
        """
        DELETE FROM department_subject AS legacy
         USING subject
         WHERE legacy.subject_id = subject.id
           AND subject.education_activity_id IS NOT NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM education_activity_department AS canonical
                WHERE canonical.education_activity_id = subject.education_activity_id
                  AND canonical.department_id = legacy.department_id
                  AND canonical.is_active IS TRUE
                  AND canonical.valid_from IS NULL
           )
        """
    ))


def downgrade():
    # The legacy rows are an adapter for canonical data and remain valid.
    pass
