"""Persistent named views (saved filters) per user.

Sessions 65+: пользователь может сохранять «свои» наборы фильтров на
страницах со списками — реестр инцидентов, /incidents/my и т.д.
Каждый view хранится для конкретного user+scope (например, scope='inc_my').
"""
from datetime import datetime

from app.core.extensions import db


class SavedView(db.Model):
    __tablename__ = "saved_view"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    scope = db.Column(db.String(40), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    qs = db.Column(db.String(1000), nullable=False, default="")
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        db.Index("ix_saved_view_user_scope", "user_id", "scope"),
        db.UniqueConstraint("user_id", "scope", "name", name="uq_saved_view_user_scope_name"),
    )
