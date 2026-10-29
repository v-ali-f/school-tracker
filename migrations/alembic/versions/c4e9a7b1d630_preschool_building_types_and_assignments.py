"""Classify preschool buildings and allow several responsible employees.

Revision ID: c4e9a7b1d630
Revises: f3c8d1a7e920
"""

from alembic import op
import sqlalchemy as sa


revision = "c4e9a7b1d630"
down_revision = "f3c8d1a7e920"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "is_preschool" not in {column["name"] for column in inspector.get_columns("buildings")}:
        op.add_column(
            "buildings",
            sa.Column("is_preschool", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        for building_id, name in bind.execute(sa.text("SELECT id, name FROM buildings")):
            if any(word in (name or "").casefold() for word in ("дошколь", "детский сад", "доу")):
                bind.execute(
                    sa.text("UPDATE buildings SET is_preschool = :enabled WHERE id = :building_id"),
                    {"enabled": True, "building_id": building_id},
                )

    if "preschool_responsibility" in inspector.get_table_names():
        bind.execute(sa.text("DELETE FROM preschool_responsibility WHERE user_id IS NULL"))
        indexes = {index["name"]: index for index in inspector.get_indexes("preschool_responsibility")}
        old_index = indexes.get("ix_preschool_responsibility_kind")
        if old_index and old_index["unique"]:
            op.drop_index("ix_preschool_responsibility_kind", table_name="preschool_responsibility")
            op.create_index("ix_preschool_responsibility_kind", "preschool_responsibility", ["kind"])
        if "uq_preschool_responsibility_kind_user" not in indexes:
            op.create_index(
                "uq_preschool_responsibility_kind_user",
                "preschool_responsibility",
                ["kind", "user_id"],
                unique=True,
            )
        bind.execute(sa.text("""
            INSERT INTO preschool_responsibility (kind, user_id, assigned_by_user_id, updated_at)
            SELECT 'SENIOR_EDUCATOR', chief.user_id, chief.assigned_by_user_id, CURRENT_TIMESTAMP
            FROM preschool_responsibility AS chief
            WHERE chief.kind = 'CHIEF_EDUCATOR'
              AND NOT EXISTS (
                  SELECT 1 FROM preschool_responsibility AS senior
                  WHERE senior.kind = 'SENIOR_EDUCATOR' AND senior.user_id = chief.user_id
              )
        """))

    if "preschool_role_grant" not in inspector.get_table_names():
        op.create_table(
            "preschool_role_grant",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("role_code", sa.String(40), nullable=False),
            sa.Column("granted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "role_code", name="uq_preschool_role_grant"),
        )
        op.create_index("ix_preschool_role_grant_user_id", "preschool_role_grant", ["user_id"])


def downgrade():
    bind = op.get_bind()
    duplicates = bind.execute(sa.text(
        "SELECT kind FROM preschool_responsibility GROUP BY kind HAVING count(*) > 1 LIMIT 1"
    )).first()
    if duplicates:
        raise RuntimeError("Remove extra preschool responsibility assignments before downgrading")
    op.drop_index("ix_preschool_role_grant_user_id", table_name="preschool_role_grant")
    op.drop_table("preschool_role_grant")
    op.drop_index("uq_preschool_responsibility_kind_user", table_name="preschool_responsibility")
    op.drop_index("ix_preschool_responsibility_kind", table_name="preschool_responsibility")
    op.create_index("ix_preschool_responsibility_kind", "preschool_responsibility", ["kind"], unique=True)
    op.drop_column("buildings", "is_preschool")
