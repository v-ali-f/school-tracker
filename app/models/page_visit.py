"""Журнал переходов пользователей по страницам.

Лог пишется through-request hook'ом в `app/core/page_visit.py`.
Источник для аналитики маршрутов на /admin/users/paths.
"""
from datetime import datetime

from app.core.extensions import db


class PageVisit(db.Model):
    __tablename__ = "page_visit"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    endpoint = db.Column(db.String(200), nullable=False)
    method = db.Column(db.String(10), nullable=False, default="GET")
    path = db.Column(db.String(500), nullable=False)
    referrer_endpoint = db.Column(db.String(200), nullable=True)
    status_code = db.Column(db.Integer, nullable=False, default=200)

    ts = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        db.Index("ix_page_visit_user_ts", "user_id", "ts"),
        db.Index("ix_page_visit_ts", "ts"),
        db.Index("ix_page_visit_endpoint_ts", "endpoint", "ts"),
    )
