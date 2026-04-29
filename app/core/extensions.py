from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
csrf = CSRFProtect()


# SQLite `LOWER()` по умолчанию работает только с ASCII: 'Сидорова' → 'Сидорова'.
# Переопределяем его через create_function, чтобы `func.lower(col)` в запросах
# корректно сравнивал кириллицу. На PostgreSQL (prod) это событие не стреляет
# — там LOWER нативно юникод-aware.
@event.listens_for(Engine, "connect")
def _sqlite_unicode_lower(dbapi_connection, connection_record):
    try:
        import sqlite3
        if isinstance(dbapi_connection, sqlite3.Connection):
            dbapi_connection.create_function("lower", 1, lambda s: s.lower() if isinstance(s, str) else s)
            dbapi_connection.create_function("upper", 1, lambda s: s.upper() if isinstance(s, str) else s)
    except Exception:
        pass


def init_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
