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

    with app.app_context():
        from app import models as app_models  # noqa: F401
        from app import attendance as attendance_module  # noqa: F401
        from app.bootstrap import ensure_runtime_schema
        from app.services.org_settings_service import ensure_single_active_organization_settings
        from app.role_access_admin import role_access_admin_bp
        from app.models.role_access import DashboardBlockCatalog
        db.create_all()
        ensure_runtime_schema()
        app.register_blueprint(role_access_admin_bp)
        try:
            ensure_single_active_organization_settings()
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            default_blocks = [
                ("home_search", "Быстрый поиск", "dashboard", 10),
                ("home_summary", "Быстрая сводка", "dashboard", 20),
                ("home_quick_links", "Быстрый доступ", "dashboard", 30),
                ("home_sections", "Тематические разделы", "dashboard", 40),
            ]
            for block_code, title, category, default_order in default_blocks:
                exists = DashboardBlockCatalog.query.filter_by(block_code=block_code).first()
                if not exists:
                    db.session.add(DashboardBlockCatalog(
                        block_code=block_code,
                        title=title,
                        category=category,
                        default_order=default_order,
                        is_active=True,
                    ))
            db.session.commit()
        except Exception:
            db.session.rollback()

        kpp_user = User.query.filter_by(username="KPP").first()
        if not kpp_user:
            kpp_user = User(username="KPP", role="KPP", last_name="КПП", first_name="Пост")
            kpp_user.set_password("123")
            db.session.add(kpp_user)
            db.session.commit()

    app.logger.info("UPLOAD_FOLDER = %s", app.config.get("UPLOAD_FOLDER"))

    return app