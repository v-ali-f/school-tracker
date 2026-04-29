"""Снимок агрегации Кубка школы — локальный кеш данных из Google Sheets."""
from datetime import datetime

from app.core.extensions import db


class ClassRatingSnapshot(db.Model):
    __tablename__ = "class_rating_snapshot"

    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(32), nullable=False, index=True)
    year_label = db.Column(db.String(16), nullable=False, default="25-26", index=True)

    place = db.Column(db.Integer, nullable=True)
    total_classes = db.Column(db.Integer, nullable=True)
    total_points = db.Column(db.Float, nullable=False, default=0.0)

    # JSON [{"name": "...", "points": 150.0}, ...] — отсортированы по убыванию баллов
    activities_json = db.Column(db.Text, nullable=True)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("class_name", "year_label", name="uq_class_rating_year"),
    )

    def __repr__(self):
        return f"<ClassRatingSnapshot {self.class_name} place={self.place} pts={self.total_points}>"


__all__ = ["ClassRatingSnapshot"]
