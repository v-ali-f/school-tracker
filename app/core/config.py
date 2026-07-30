import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
INSTANCE_DIR = BASE_DIR / "instance"
UPLOADS_DIR = BASE_DIR / "uploads"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-later")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'app.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(UPLOADS_DIR))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 200 * 1024 * 1024))
    APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip()
    FIREBASE_SERVICE_ACCOUNT_FILE = os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE", "").strip()
    FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "").strip()
    FIREBASE_WEB_AUTH_DOMAIN = os.getenv("FIREBASE_WEB_AUTH_DOMAIN", "").strip()
    FIREBASE_WEB_PROJECT_ID = os.getenv("FIREBASE_WEB_PROJECT_ID", "").strip()
    FIREBASE_WEB_STORAGE_BUCKET = os.getenv("FIREBASE_WEB_STORAGE_BUCKET", "").strip()
    FIREBASE_WEB_MESSAGING_SENDER_ID = os.getenv("FIREBASE_WEB_MESSAGING_SENDER_ID", "").strip()
    FIREBASE_WEB_APP_ID = os.getenv("FIREBASE_WEB_APP_ID", "").strip()
    FIREBASE_WEB_MEASUREMENT_ID = os.getenv("FIREBASE_WEB_MEASUREMENT_ID", "").strip()
    FIREBASE_WEB_VAPID_KEY = os.getenv("FIREBASE_WEB_VAPID_KEY", "").strip()
    PWA_BADGE_POLL_INTERVAL_MS = max(
        15000,
        int(os.getenv("PWA_BADGE_POLL_INTERVAL_MS", "60000") or "60000"),
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    AUTO_SCHEMA_BOOTSTRAP = _env_bool("AUTO_SCHEMA_BOOTSTRAP", True)
    FEATURE_WORKLOAD_MODULE_ENABLED = _env_bool("FEATURE_WORKLOAD_MODULE_ENABLED", False)
    FEATURE_WORKLOAD_WRITE_ENABLED = _env_bool("FEATURE_WORKLOAD_WRITE_ENABLED", False)
    FEATURE_WORKLOAD_NEW_SOURCE_ENABLED = _env_bool("FEATURE_WORKLOAD_NEW_SOURCE_ENABLED", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


class ProductionConfig(Config):
    DEBUG = False


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def configure_app(app):
    config_name = os.getenv("FLASK_ENV", "default")
    config_class = CONFIG_MAP.get(config_name, DevelopmentConfig)
    app.config.from_object(config_class)
    INSTANCE_DIR.mkdir(exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    return app
