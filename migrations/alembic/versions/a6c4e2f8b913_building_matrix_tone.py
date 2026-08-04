"""Add configurable building colors for registry matrices.

Revision ID: a6c4e2f8b913
Revises: d8f2a6c4e901
"""

from alembic import op
import sqlalchemy as sa


revision = "a6c4e2f8b913"
down_revision = "d8f2a6c4e901"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("buildings", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "matrix_tone",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ))
        batch_op.create_check_constraint(
            "ck_buildings_matrix_tone",
            "matrix_tone IN (0,1,2,3,4,5)",
        )

    op.execute(
        sa.text(
            """
            UPDATE buildings
            SET matrix_tone = CASE
                WHEN lower(name) LIKE :sechenov
                  OR lower(name) LIKE :ushakov
                THEN 1
                ELSE 0
            END
            """
        ).bindparams(
            sechenov="%сеченов%",
            ushakov="%ушаков%",
        )
    )


def downgrade():
    with op.batch_alter_table("buildings", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_buildings_matrix_tone",
            type_="check",
        )
        batch_op.drop_column("matrix_tone")
