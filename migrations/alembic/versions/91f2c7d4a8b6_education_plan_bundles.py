"""Link curriculum, extracurricular and additional plan parts.

Revision ID: 91f2c7d4a8b6
Revises: b84d2e6f7a13
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "91f2c7d4a8b6"
down_revision = "b84d2e6f7a13"
branch_labels = None
depends_on = None


COMPANION_LABELS = {
    "EXTRACURRICULAR": "Внеурочная деятельность",
    "ADDITIONAL_EDUCATION": "Дополнительное образование",
}


def _same_nullable(left, right):
    return left == right or (left is None and right is None)


def upgrade():
    op.add_column(
        "education_plan",
        sa.Column("root_plan_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_education_plan_root_plan",
        "education_plan",
        "education_plan",
        ["root_plan_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_education_plan_root_plan_id",
        "education_plan",
        ["root_plan_id"],
        unique=False,
    )
    op.create_index(
        "uq_education_plan_root_kind",
        "education_plan",
        ["root_plan_id", "plan_kind"],
        unique=True,
        postgresql_where=sa.text("root_plan_id IS NOT NULL"),
        sqlite_where=sa.text("root_plan_id IS NOT NULL"),
    )
    op.create_check_constraint(
        "ck_education_plan_companion_kind",
        "education_plan",
        "root_plan_id IS NULL OR plan_kind <> 'CURRICULUM'",
    )

    connection = op.get_bind()
    plans = list(connection.execute(sa.text(
        """
        SELECT id, tariff_version_id, plan_kind, name, education_level,
               building_id, scope_code, status, revision,
               created_by_user_id, updated_by_user_id
          FROM education_plan
         ORDER BY id
        """
    )).mappings())
    roots = [item for item in plans if item["plan_kind"] == "CURRICULUM"]
    claimed_companion_ids = set()

    for root in roots:
        for plan_kind, label in COMPANION_LABELS.items():
            matches = [
                item
                for item in plans
                if (
                    item["id"] not in claimed_companion_ids
                    and item["plan_kind"] == plan_kind
                    and item["tariff_version_id"]
                    == root["tariff_version_id"]
                    and item["scope_code"] == root["scope_code"]
                    and _same_nullable(
                        item["education_level"],
                        root["education_level"],
                    )
                    and _same_nullable(
                        item["building_id"],
                        root["building_id"],
                    )
                )
            ]
            if matches:
                claimed_companion_ids.add(matches[0]["id"])
                connection.execute(
                    sa.text(
                        """
                        UPDATE education_plan
                           SET root_plan_id = :root_plan_id
                         WHERE id = :plan_id
                        """
                    ),
                    {
                        "root_plan_id": root["id"],
                        "plan_id": matches[0]["id"],
                    },
                )
                continue

            now = datetime.utcnow()
            connection.execute(
                sa.text(
                    """
                    INSERT INTO education_plan (
                        tariff_version_id, root_plan_id, plan_kind, name,
                        education_level, building_id, scope_code, status,
                        revision, created_by_user_id, updated_by_user_id,
                        created_at, updated_at
                    ) VALUES (
                        :tariff_version_id, :root_plan_id, :plan_kind, :name,
                        :education_level, :building_id, :scope_code, :status,
                        1, :created_by_user_id, :updated_by_user_id,
                        :created_at, :updated_at
                    )
                    """
                ),
                {
                    "tariff_version_id": root["tariff_version_id"],
                    "root_plan_id": root["id"],
                    "plan_kind": plan_kind,
                    "name": f"{root['name']} · {label}"[:255],
                    "education_level": root["education_level"],
                    "building_id": root["building_id"],
                    "scope_code": root["scope_code"],
                    "status": root["status"],
                    "created_by_user_id": root["created_by_user_id"],
                    "updated_by_user_id": root["updated_by_user_id"],
                    "created_at": now,
                    "updated_at": now,
                },
            )


def downgrade():
    op.drop_constraint(
        "ck_education_plan_companion_kind",
        "education_plan",
        type_="check",
    )
    op.drop_index(
        "uq_education_plan_root_kind",
        table_name="education_plan",
    )
    op.drop_index(
        "ix_education_plan_root_plan_id",
        table_name="education_plan",
    )
    op.drop_constraint(
        "fk_education_plan_root_plan",
        "education_plan",
        type_="foreignkey",
    )
    op.drop_column("education_plan", "root_plan_id")
