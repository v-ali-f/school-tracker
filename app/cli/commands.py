import click
from flask.cli import with_appcontext

from app.bootstrap import ensure_runtime_schema, seed_olympiad_subject_mappings
from app.core.extensions import db


def register_cli(app):
    @app.cli.command("init-db")
    @with_appcontext
    def init_db_command():
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("repair-runtime-columns")
    @with_appcontext
    def repair_runtime_columns_command():
        ensure_runtime_schema()
        click.echo("Runtime schema repair finished.")

    @app.cli.command("seed-olympiads")
    @with_appcontext
    def seed_olympiads_command():
        created = seed_olympiad_subject_mappings(app)
        click.echo(f"Olympiad mappings created: {created}")

    @app.cli.command("seed-academic-year")
    @with_appcontext
    @click.option("--name", default="2025/2026", show_default=True)
    def seed_academic_year_command(name):
        from app.models import AcademicYear
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

    @app.cli.command("seed-initial-data")
    @with_appcontext
    def seed_initial_data_command():
        from app.models import Role, Department, Subject, AcademicYear

        created = []
        role_codes = [
            ("ADMIN", "Администратор"),
            ("MANAGEMENT", "Администрация"),
            ("TEACHER", "Учитель"),
            ("CURATOR", "Куратор"),
            ("VIEWER", "Наблюдатель"),
        ]
        for code, name in role_codes:
            if not Role.query.filter_by(code=code).first():
                db.session.add(Role(code=code, name=name))
                created.append(f"role:{code}")

        for dep_name in ["Начальная школа", "Математика", "Русский язык", "Иностранные языки", "Естественные науки"]:
            if not Department.query.filter_by(name=dep_name).first():
                db.session.add(Department(name=dep_name))
                created.append(f"department:{dep_name}")

        for subj_name in ["Математика", "Русский язык", "Литература", "Информатика", "Физика", "Биология", "История", "Английский язык"]:
            if not Subject.query.filter_by(name=subj_name).first():
                db.session.add(Subject(name=subj_name))
                created.append(f"subject:{subj_name}")

        if not AcademicYear.query.filter_by(is_current=True).first():
            db.session.add(AcademicYear(name="2025/2026", is_current=True))
            created.append("academic_year:2025/2026")

        db.session.commit()
        click.echo("Initial data seeded: " + (", ".join(created) if created else "nothing new"))

    @app.cli.command("create-admin")
    @with_appcontext
    @click.option("--username", default="admin", show_default=True)
    @click.option("--password", default="admin123", show_default=True)
    @click.option("--last-name", default="Администратор", show_default=True)
    @click.option("--first-name", default="Системы", show_default=True)
    def create_admin_command(username, password, last_name, first_name):
        from app.models import User

        user = User.query.filter_by(username=username).first()
        if user:
            user.role = "ADMIN"
            user.last_name = user.last_name or last_name
            user.first_name = user.first_name or first_name
            user.set_password(password)
            db.session.commit()
            click.echo(f"Admin updated: {username}")
            return

        user = User(
            username=username,
            role="ADMIN",
            last_name=last_name,
            first_name=first_name,
            is_active_user=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin created: {username}")
