"""Upgrade checks for building types and multiple preschool appointments."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


VERSIONS = Path(__file__).resolve().parents[1] / "migrations/alembic/versions"


def _load(filename):
    spec = importlib.util.spec_from_file_location(filename, VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_keeps_old_assignments_and_allows_multiple_people():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE user (id INTEGER PRIMARY KEY, name TEXT)")
        connection.exec_driver_sql("CREATE TABLE buildings (id INTEGER PRIMARY KEY, name TEXT)")
        connection.exec_driver_sql("CREATE TABLE academic_year (id INTEGER PRIMARY KEY, name TEXT)")
        connection.exec_driver_sql("CREATE TABLE preschool_group (id INTEGER PRIMARY KEY, name TEXT)")
        connection.exec_driver_sql("CREATE TABLE preschool_child (id INTEGER PRIMARY KEY, name TEXT)")
        connection.exec_driver_sql("INSERT INTO user (id, name) VALUES (1, 'A'), (2, 'B'), (3, 'C')")
        connection.exec_driver_sql(
            "INSERT INTO buildings (id, name) VALUES (1, 'Школьный корпус'), (2, 'Дошкольный корпус 1')"
        )
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            _load("f3c8d1a7e920_preschool_staff_and_shared_records.py").upgrade()
            connection.exec_driver_sql(
                "INSERT INTO preschool_responsibility (kind, user_id) "
                "VALUES ('CONTINGENT_MANAGER', 1), ('CHIEF_EDUCATOR', 2)"
            )
            migration = _load("c4e9a7b1d630_preschool_building_types_and_assignments.py")
            migration.upgrade()
            migration.upgrade()

        assert connection.exec_driver_sql(
            "SELECT id, is_preschool FROM buildings ORDER BY id"
        ).all() == [(1, 0), (2, 1)]
        assert connection.exec_driver_sql(
            "SELECT kind, user_id FROM preschool_responsibility ORDER BY kind, user_id"
        ).all() == [
            ("CHIEF_EDUCATOR", 2), ("CONTINGENT_MANAGER", 1), ("SENIOR_EDUCATOR", 2),
        ]
        connection.exec_driver_sql(
            "INSERT INTO preschool_responsibility (kind, user_id) VALUES ('CONTINGENT_MANAGER', 3)"
        )
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM preschool_responsibility WHERE kind='CONTINGENT_MANAGER'"
        ).scalar_one() == 2
        assert "preschool_role_grant" in sa.inspect(connection).get_table_names()
