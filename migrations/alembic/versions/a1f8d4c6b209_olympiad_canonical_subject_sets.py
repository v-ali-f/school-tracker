"""Store olympiad linked subjects as canonical education activities.

Revision ID: a1f8d4c6b209
Revises: 9e7c3f5a2b41
"""

from alembic import op
import sqlalchemy as sa


revision = "a1f8d4c6b209"
down_revision = "9e7c3f5a2b41"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "olympiad_subject_mapping",
        sa.Column("linked_education_activity_ids", sa.Text(), nullable=True),
    )
    connection = op.get_bind()
    connection.execute(sa.text(
        """
        UPDATE olympiad_subject_mapping AS mapping
           SET linked_education_activity_ids = converted.activity_ids
          FROM (
               SELECT source.id,
                      string_agg(
                          DISTINCT subject.education_activity_id::text,
                          ',' ORDER BY subject.education_activity_id::text
                      ) AS activity_ids
                 FROM olympiad_subject_mapping AS source
                 CROSS JOIN LATERAL regexp_split_to_table(
                     replace(coalesce(source.linked_subject_ids, ''), ';', ','),
                     ','
                 ) AS split_value(raw_subject_id)
                 JOIN subject
                   ON subject.id = CASE
                       WHEN trim(raw_subject_id) ~ '^[0-9]+$'
                       THEN trim(raw_subject_id)::integer
                       ELSE NULL
                   END
                WHERE subject.education_activity_id IS NOT NULL
                GROUP BY source.id
          ) AS converted
         WHERE mapping.id = converted.id
        """
    ))
    connection.execute(sa.text(
        """
        UPDATE olympiad_subject_mapping
           SET linked_education_activity_ids = education_activity_id::text
         WHERE education_activity_id IS NOT NULL
           AND (
               linked_education_activity_ids IS NULL
               OR linked_education_activity_ids = ''
           )
        """
    ))


def downgrade():
    op.drop_column(
        "olympiad_subject_mapping",
        "linked_education_activity_ids",
    )
