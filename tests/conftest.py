import os

import pytest


os.environ["FLASK_ENV"] = "testing"
os.environ["TEST_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SCHEMA_BOOTSTRAP"] = "0"
os.environ["UPLOAD_FOLDER"] = "/private/tmp/altair-test-storage/uploads"
os.environ["KUBOK_SCHEDULER_DISABLED"] = "1"
os.environ["FEATURE_WORKLOAD_MODULE_ENABLED"] = "0"
os.environ["FEATURE_WORKLOAD_WRITE_ENABLED"] = "0"
os.environ["FEATURE_WORKLOAD_NEW_SOURCE_ENABLED"] = "0"

from app import create_app
from app.core.extensions import db
from app.models import User


@pytest.fixture()
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        FEATURE_WORKLOAD_MODULE_ENABLED=False,
        FEATURE_WORKLOAD_WRITE_ENABLED=False,
        FEATURE_WORKLOAD_NEW_SOURCE_ENABLED=False,
    )

    with application.app_context():
        db.create_all()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_user(app):
    counter = 0

    def factory(role="VIEWER"):
        nonlocal counter
        counter += 1
        with app.app_context():
            user = User(
                username=f"test-user-{counter}",
                role=role,
                last_name="Тестов",
                first_name="Пользователь",
            )
            user.set_password("local-test-password")
            db.session.add(user)
            db.session.commit()
            return user.id

    return factory


@pytest.fixture()
def login(client):
    def factory(user_id):
        with client.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True

    return factory
