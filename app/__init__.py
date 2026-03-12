import os
from dotenv import load_dotenv
from flask import Flask

from app.core.extensions import db, migrate, login_manager
from app.core import (
    configure_app,
    configure_logging,
    init_extensions,
    register_blueprints,
    register_context_processors,
)

from app.cli import register_cli

load_dotenv(override=True)


def get_current_year():
    from app.models import AcademicYear
    return AcademicYear.query.filter_by(is_current=True).first()


def create_app():
    app = Flask(__name__)

    configure_app(app)
    configure_logging(app)
    init_extensions(app)

    from app.permissions import has_permission, build_menu_flags
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    register_context_processors(app, has_permission, build_menu_flags)
    register_blueprints(app)
    register_cli(app)

    app.logger.info("DATABASE = %s", app.config.get("SQLALCHEMY_DATABASE_URI"))
    app.logger.info("UPLOAD_FOLDER = %s", app.config.get("UPLOAD_FOLDER"))

    return app