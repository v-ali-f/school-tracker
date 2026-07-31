import click
from flask.cli import with_appcontext

from app.bootstrap import ensure_runtime_schema, seed_olympiad_subject_mappings
from app.core.extensions import db


def register_cli(app):
    @app.cli.command("init-db")
    @with_appcontext
    def init_db_command():
        try:
            db.create_all()
            click.echo("Database tables created or already exist.")
        except Exception as exc:
            raise click.ClickException(f"init-db failed: {exc}")

    @app.cli.command("repair-runtime-columns")
    @with_appcontext
    def repair_runtime_columns_command():
        try:
            ensure_runtime_schema()
            click.echo("Runtime schema repair finished.")
        except Exception as exc:
            raise click.ClickException(f"repair-runtime-columns failed: {exc}")

    @app.cli.command("seed-olympiads")
    @with_appcontext
    def seed_olympiads_command():
        try:
            created = seed_olympiad_subject_mappings(app)
            click.echo(f"Olympiad mappings created: {created}")
        except Exception as exc:
            raise click.ClickException(f"seed-olympiads failed: {exc}")

    @app.cli.command("seed-academic-year")
    @with_appcontext
    @click.option("--name", default="2025/2026", show_default=True)
    def seed_academic_year_command(name):
        from app.models import AcademicYear
        try:
            year = AcademicYear.query.filter_by(name=name).first()
            if not year:
                AcademicYear.query.update({AcademicYear.is_current: False})
                year = AcademicYear(name=name, is_current=True)
                db.session.add(year)
                db.session.commit()
                click.echo(f"Academic year created: {name}")
            else:
                AcademicYear.query.update({AcademicYear.is_current: False})
                year.is_current = True
                db.session.commit()
                click.echo(f"Academic year updated as current: {name}")
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException(f"seed-academic-year failed: {exc}")

    @app.cli.command("seed-initial-data")
    @with_appcontext
    def seed_initial_data_command():
        from app.models import Role, Department, AcademicYear
        from app.services.education_activity_service import (
            get_or_create_subject_activity,
        )
        try:
            created = []
            role_codes = [("ADMIN", "Администратор"), ("MANAGEMENT", "Администрация"), ("TEACHER", "Учитель"), ("CURATOR", "Куратор"), ("VIEWER", "Наблюдатель")]
            for code, name in role_codes:
                if not Role.query.filter_by(code=code).first():
                    db.session.add(Role(code=code, name=name))
                    created.append(f"role:{code}")
            for dep_name in ["Начальная школа", "Математика", "Русский язык", "Иностранные языки", "Естественные науки"]:
                if not Department.query.filter_by(name=dep_name).first():
                    db.session.add(Department(name=dep_name))
                    created.append(f"department:{dep_name}")
            for subj_name in ["Математика", "Русский язык", "Литература", "Информатика", "Физика", "Биология", "История", "Английский язык"]:
                _activity, subject_created = get_or_create_subject_activity(subj_name)
                if subject_created:
                    created.append(f"subject:{subj_name}")
            if not AcademicYear.query.filter_by(is_current=True).first():
                db.session.add(AcademicYear(name="2025/2026", is_current=True))
                created.append("academic_year:2025/2026")
            db.session.commit()
            click.echo("Initial data seeded: " + (", ".join(created) if created else "nothing new"))
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException(f"seed-initial-data failed: {exc}")

    @app.cli.command("create-admin")
    @with_appcontext
    @click.option("--username", default="admin", show_default=True)
    @click.option("--password", default="admin123", show_default=True)
    @click.option("--last-name", default="Администратор", show_default=True)
    @click.option("--first-name", default="Системы", show_default=True)
    def create_admin_command(username, password, last_name, first_name):
        from app.models import User
        try:
            user = User.query.filter_by(username=username).first()
            if user:
                user.role = "ADMIN"
                user.last_name = user.last_name or last_name
                user.first_name = user.first_name or first_name
                user.set_password(password)
                db.session.commit()
                click.echo(f"Admin updated: {username}")
                return
            user = User(username=username, role="ADMIN", last_name=last_name, first_name=first_name, is_active_user=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            click.echo(f"Admin created: {username}")
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException(f"create-admin failed: {exc}")

    @app.cli.command("refresh-kubok")
    @with_appcontext
    def refresh_kubok_command():
        """Скачать Google Sheets Кубка школы и пересобрать локальный кеш."""
        from app.kubok import refresh_cache
        try:
            count, when = refresh_cache()
            click.echo(f"Kubok cache refreshed: {count} classes at {when.isoformat()}")
        except Exception as exc:
            raise click.ClickException(f"refresh-kubok failed: {exc}")

    @app.cli.command("apply-performance-indexes")
    @with_appcontext
    def apply_performance_indexes_command():
        from sqlalchemy import inspect, text as sql_text

        inspector = inspect(db.engine)

        def has_table(table_name):
            return table_name in inspector.get_table_names()

        def has_columns(table_name, *columns):
            if not has_table(table_name):
                return False
            existing = {col["name"] for col in inspector.get_columns(table_name)}
            return all(col in existing for col in columns)

        statements = []
        if has_columns("child", "last_name", "first_name", "middle_name"):
            statements.append("CREATE INDEX IF NOT EXISTS ix_child_name_parts ON child(last_name, first_name, middle_name)")
        if has_columns("school_class", "grade", "building_id"):
            statements.append("CREATE INDEX IF NOT EXISTS ix_school_class_grade_building ON school_class(grade, building_id)")
        if has_columns("attendance_raw_entry", "child_id", "entry_date"):
            statements.append("CREATE INDEX IF NOT EXISTS ix_attendance_raw_entry_child_entry_date ON attendance_raw_entry(child_id, entry_date)")
        if has_columns("attendance_raw_entry", "entry_date", "matched_class_id"):
            statements.append("CREATE INDEX IF NOT EXISTS ix_attendance_raw_entry_entry_date_class ON attendance_raw_entry(entry_date, matched_class_id)")
        if has_columns("attendance_late", "late_date", "class_id"):
            statements.append("CREATE INDEX IF NOT EXISTS ix_attendance_late_date_class ON attendance_late(late_date, class_id)")
        if has_columns("attendance_import_session", "period_year", "period_num"):
            statements.append("CREATE INDEX IF NOT EXISTS ix_attendance_import_session_year_month ON attendance_import_session(period_year, period_num)")
        elif has_columns("attendance_import_session", "period_month"):
            statements.append("CREATE INDEX IF NOT EXISTS ix_attendance_import_session_period_month ON attendance_import_session(period_month)")
        if has_columns("attendance_import_session", "building_id"):
            statements.append("CREATE INDEX IF NOT EXISTS ix_attendance_import_session_building_id ON attendance_import_session(building_id)")
        if has_columns("attendance_import_session", "imported_at"):
            statements.append("CREATE INDEX IF NOT EXISTS ix_attendance_import_session_imported_at ON attendance_import_session(imported_at)")

        try:
            for stmt in statements:
                db.session.execute(sql_text(stmt))
            db.session.commit()
            click.echo(f"Performance indexes applied: {len(statements)}")
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException(f"apply-performance-indexes failed: {exc}")
