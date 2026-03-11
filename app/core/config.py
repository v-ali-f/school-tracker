import os

def configure_app(app):
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-later")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    upload_dir = os.getenv("UPLOAD_FOLDER", os.path.abspath(os.path.join("data", "uploads")))
    os.makedirs(upload_dir, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_dir
    return app
