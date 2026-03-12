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
    def seed_academic_year_command():
        try:
            from app.seed_year import ensure_current_academic_year
            created = ensure_current_academic_year()
            click.echo(f"Academic year seed finished: {created}")
        except Exception as exc:
            click.echo(f"Academic year seed failed: {exc}")
