"""Release checks against a small legacy preschool schema and existing data."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION = Path(__file__).resolve().parents[1] / "migrations/alembic/versions/f3c8d1a7e920_preschool_staff_and_shared_records.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("preschool_release_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_preserves_legacy_counts_and_can_run_twice():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        for table in ("user", "buildings", "academic_year", "preschool_group", "preschool_child"):
            connection.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, name TEXT)")
            connection.exec_driver_sql(f"INSERT INTO {table} (id, name) VALUES (1, 'legacy')")
        connection.exec_driver_sql("CREATE TABLE preschool_child_movement (id INTEGER PRIMARY KEY, child_id INTEGER)")
        connection.exec_driver_sql("INSERT INTO preschool_child_movement (id, child_id) VALUES (1, 1)")
        connection.exec_driver_sql("CREATE TABLE teacher_mcko_result (id INTEGER PRIMARY KEY, teacher_id INTEGER)")
        connection.exec_driver_sql("INSERT INTO teacher_mcko_result (id, teacher_id) VALUES (1, 1)")
        connection.exec_driver_sql("CREATE TABLE teacher_course (id INTEGER PRIMARY KEY, teacher_id INTEGER)")
        connection.exec_driver_sql("INSERT INTO teacher_course (id, teacher_id) VALUES (1, 1)")
        before = {table: connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
                  for table in ("preschool_group", "preschool_child", "preschool_child_movement", "teacher_mcko_result", "teacher_course")}
        migration = _migration_module()
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
            migration.upgrade()
        after = {table: connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
                 for table in before}
        assert after == before
        assert "preschool_group_assignment" in sa.inspect(connection).get_table_names()
        assert "preschool_achievement" in sa.inspect(connection).get_table_names()
        assert "document_number" in {column["name"] for column in sa.inspect(connection).get_columns("teacher_course")}
