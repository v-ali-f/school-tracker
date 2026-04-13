from .academic import academic_bp
from .analytics import analytics_bp
from .attendance import attendance_bp
from .auth import auth_bp
from .children import children_bp
from .classes import classes_bp
from .control_works import control_bp
from .debts import debts_bp
from .diagnostics import diagnostics_bp
from .departments import departments_bp
from .documents import documents_bp
from .imports import import_bp
from .main import main_bp
from .management import management_bp
from .olympiads import olympiads_bp
from .orders import orders_bp
from .organization_settings import organization_settings_bp
from .reports import reports_bp
from .transfers import transfers_bp
from .users import users_bp
from .hub import hub_bp
from .service_staff import service_staff_bp
from .iom import iom_bp
from .tasks import tasks_bp
from .school_plan import school_plan_bp
from app.knowledge import knowledge_bp

BLUEPRINTS = [
    main_bp,
    reports_bp,
    auth_bp,
    children_bp,
    debts_bp,
    diagnostics_bp,
    documents_bp,
    analytics_bp,
    attendance_bp,
    import_bp,
    users_bp,
    classes_bp,
    control_bp,
    departments_bp,
    transfers_bp,
    management_bp,
    academic_bp,
    orders_bp,
    organization_settings_bp,
    olympiads_bp,
    hub_bp,
    service_staff_bp,
    iom_bp,
    tasks_bp,
    school_plan_bp,
    knowledge_bp,
]


def register_blueprints(app):
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)
