"""Allow a plan set to be selected for 10th and 11th classes."""

from alembic import op
import sqlalchemy as sa


revision = "f1a7c3e9b204"
down_revision = "a6c4e2f8b913"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        "education_plan_binding",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_education_plan_binding_mode",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_education_plan_binding_mode",
            "binding_mode IN ('CLASS','STUDENTS','PLAN_SET')",
        )


def downgrade():
    op.execute(
        sa.text(
            "UPDATE education_plan_binding "
            "SET binding_mode = 'STUDENTS' "
            "WHERE binding_mode = 'PLAN_SET'"
        )
    )
    with op.batch_alter_table(
        "education_plan_binding",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_education_plan_binding_mode",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_education_plan_binding_mode",
            "binding_mode IN ('CLASS','STUDENTS')",
        )
