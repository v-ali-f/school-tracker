import os


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-change-later')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', os.path.abspath(os.path.join('data', 'uploads')))
