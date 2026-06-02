"""Привязка пользователя портала к MAX-боту (бот для подачи инцидентов).

Поток:
1. Пользователь на /profile/max жмёт «Привязать» → создаём MaxBinding(status='pending', code=6-digit, TTL 10 мин).
2. В MAX он шлёт боту `/start <code>`.
3. APScheduler-job на портале раз в 15с забирает у бота pending_binds → ищет
   MaxBinding по коду → переводит в 'done', записывает max_chat_id.
4. Поиск активной привязки: status='done', самая свежая по user_id.
"""
from datetime import datetime

from app.core.extensions import db


class MaxBinding(db.Model):
    __tablename__ = "max_binding"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    code = db.Column(db.String(6), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="pending", index=True)  # pending|done|expired|revoked
    max_chat_id = db.Column(db.BigInteger, nullable=True, index=True)
    max_full_name = db.Column(db.String(160), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    bound_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        db.Index("ix_max_binding_user_status", "user_id", "status"),
    )
