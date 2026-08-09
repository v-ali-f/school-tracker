"""Add professional registry authorship, terms and employment start date.

Revision ID: d9b6f2c4a810
Revises: b2d7e4f9a105
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d9b6f2c4a810"
down_revision = "b2d7e4f9a105"
branch_labels = None
depends_on = None


def _columns(inspector, table_name):
    return {item["name"] for item in inspector.get_columns(table_name)}


def _fk_for_columns(inspector, table_name, column_names):
    wanted = list(column_names)
    return next(
        (
            item
            for item in inspector.get_foreign_keys(table_name)
            if item.get("constrained_columns") == wanted
        ),
        None,
    )


def _index_for_columns(inspector, table_name, column_names):
    wanted = list(column_names)
    return next(
        (
            item
            for item in inspector.get_indexes(table_name)
            if item.get("column_names") == wanted
        ),
        None,
    )


def _add_years(value, years):
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def _add_user_columns(bind):
    columns = _columns(inspect(bind), "user")
    if "employment_start_date" not in columns:
        with op.batch_alter_table("user") as batch_op:
            batch_op.add_column(
                sa.Column("employment_start_date", sa.Date(), nullable=True)
            )


def _add_mcko_columns(bind):
    columns = _columns(inspect(bind), "teacher_mcko_result")
    additions = []
    if "certificate_number" not in columns:
        additions.append(sa.Column("certificate_number", sa.String(120)))
    if "entry_source" not in columns:
        additions.append(sa.Column(
            "entry_source",
            sa.String(24),
            nullable=False,
            server_default=sa.text("'LEGACY'"),
        ))
    if "created_by_user_id" not in columns:
        additions.append(sa.Column("created_by_user_id", sa.Integer()))
    if "updated_by_user_id" not in columns:
        additions.append(sa.Column("updated_by_user_id", sa.Integer()))
    if "updated_at" not in columns:
        additions.append(sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ))
    if additions:
        with op.batch_alter_table("teacher_mcko_result") as batch_op:
            for column in additions:
                batch_op.add_column(column)

    metadata = sa.MetaData()
    table = sa.Table("teacher_mcko_result", metadata, autoload_with=bind)
    if "updated_at" in table.c and "created_at" in table.c:
        bind.execute(table.update().values(updated_at=table.c.created_at))
    if {"passed_at", "expires_at"}.issubset(table.c.keys()):
        rows = bind.execute(sa.select(
            table.c.id,
            table.c.passed_at,
            table.c.expires_at,
        )).all()
        for row in rows:
            if row.passed_at is not None and row.expires_at is None:
                bind.execute(
                    table.update()
                    .where(table.c.id == row.id)
                    .values(expires_at=_add_years(row.passed_at, 3))
                )


def _add_attestation_columns(bind):
    columns = _columns(inspect(bind), "teacher_attestation")
    additions = []
    if "is_indefinite" not in columns:
        additions.append(sa.Column(
            "is_indefinite",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ))
    if "entry_source" not in columns:
        additions.append(sa.Column(
            "entry_source",
            sa.String(24),
            nullable=False,
            server_default=sa.text("'LEGACY'"),
        ))
    if "created_by_user_id" not in columns:
        additions.append(sa.Column("created_by_user_id", sa.Integer()))
    if "updated_by_user_id" not in columns:
        additions.append(sa.Column("updated_by_user_id", sa.Integer()))
    if "updated_at" not in columns:
        additions.append(sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ))
    if additions:
        with op.batch_alter_table("teacher_attestation") as batch_op:
            for column in additions:
                batch_op.add_column(column)

    metadata = sa.MetaData()
    table = sa.Table("teacher_attestation", metadata, autoload_with=bind)
    if "updated_at" in table.c and "created_at" in table.c:
        bind.execute(table.update().values(updated_at=table.c.created_at))
    if {"is_indefinite", "valid_until", "category"}.issubset(table.c.keys()):
        bind.execute(
            table.update()
            .where(
                table.c.valid_until.is_(None),
                table.c.category.in_(["FIRST", "HIGHEST"]),
            )
            .values(is_indefinite=True)
        )


def _add_audit_constraints(bind, table_name):
    for column_name, fk_name, index_name in (
        (
            "created_by_user_id",
            f"fk_{table_name}_created_by_user",
            f"ix_{table_name}_created_by_user_id",
        ),
        (
            "updated_by_user_id",
            f"fk_{table_name}_updated_by_user",
            f"ix_{table_name}_updated_by_user_id",
        ),
    ):
        inspector = inspect(bind)
        if not _fk_for_columns(inspector, table_name, [column_name]):
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.create_foreign_key(
                    fk_name,
                    "user",
                    [column_name],
                    ["id"],
                )
        inspector = inspect(bind)
        if not _index_for_columns(inspector, table_name, [column_name]):
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.create_index(index_name, [column_name], unique=False)


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("user"):
        _add_user_columns(bind)
    if inspector.has_table("teacher_mcko_result"):
        _add_mcko_columns(bind)
        _add_audit_constraints(bind, "teacher_mcko_result")
    if inspector.has_table("teacher_attestation"):
        _add_attestation_columns(bind)
        _add_audit_constraints(bind, "teacher_attestation")


def _drop_audit_constraints(bind, table_name):
    for column_name, fk_name, index_name in (
        (
            "updated_by_user_id",
            f"fk_{table_name}_updated_by_user",
            f"ix_{table_name}_updated_by_user_id",
        ),
        (
            "created_by_user_id",
            f"fk_{table_name}_created_by_user",
            f"ix_{table_name}_created_by_user_id",
        ),
    ):
        inspector = inspect(bind)
        index = _index_for_columns(inspector, table_name, [column_name])
        if index and index.get("name") == index_name:
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.drop_index(index_name)
        inspector = inspect(bind)
        foreign_key = _fk_for_columns(inspector, table_name, [column_name])
        if foreign_key and foreign_key.get("name") == fk_name:
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.drop_constraint(fk_name, type_="foreignkey")


def _drop_columns(bind, table_name, column_names):
    columns = _columns(inspect(bind), table_name)
    with op.batch_alter_table(table_name) as batch_op:
        for column_name in column_names:
            if column_name in columns:
                batch_op.drop_column(column_name)


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("teacher_attestation"):
        _drop_audit_constraints(bind, "teacher_attestation")
        _drop_columns(bind, "teacher_attestation", [
            "updated_at",
            "updated_by_user_id",
            "created_by_user_id",
            "entry_source",
            "is_indefinite",
        ])
    inspector = inspect(bind)
    if inspector.has_table("teacher_mcko_result"):
        _drop_audit_constraints(bind, "teacher_mcko_result")
        _drop_columns(bind, "teacher_mcko_result", [
            "updated_at",
            "updated_by_user_id",
            "created_by_user_id",
            "entry_source",
            "certificate_number",
        ])
    inspector = inspect(bind)
    if inspector.has_table("user"):
        _drop_columns(bind, "user", ["employment_start_date"])
