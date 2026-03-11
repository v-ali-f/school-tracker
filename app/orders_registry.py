
from datetime import datetime
from app.extensions import db

class SchoolOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50))
    title = db.Column(db.String(255))
    section = db.Column(db.String(100))  # учебная часть, воспитательная часть, допобразование, контингент
    executor = db.Column(db.String(255))
    author = db.Column(db.String(255))
    responsible = db.Column(db.String(255))
    due_date = db.Column(db.Date)
    approved_by_deputy = db.Column(db.Boolean, default=False)
    original_submitted = db.Column(db.Boolean, default=False)
    date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
