import os
from dotenv import load_dotenv
from flask import Flask, render_template

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
        from app.core.profiler import init_profiler
        from app.core.activity import init_user_activity
        from app.core.page_visit import init_page_visit_logger
        db.create_all()
        ensure_runtime_schema()
        init_profiler(app, db.engine)
        init_user_activity(app)
        init_page_visit_logger(app)
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
            import secrets as _secrets
            kpp_password = os.getenv("KPP_INITIAL_PASSWORD") or _secrets.token_urlsafe(12)
            kpp_user = User(username="KPP", role="KPP", last_name="КПП", first_name="Пост")
            kpp_user.set_password(kpp_password)
            db.session.add(kpp_user)
            db.session.commit()
            app.logger.warning(
                "KPP user created. Initial password: %s (store in .env as KPP_INITIAL_PASSWORD to suppress this log)",
                kpp_password,
            )

    try:
        from app.scheduler import init_scheduler
        init_scheduler(app)
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("Scheduler init failed: %s", exc)

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        return render_template("errors/500.html"), 500

    app.logger.info("UPLOAD_FOLDER = %s", app.config.get("UPLOAD_FOLDER"))

    return app