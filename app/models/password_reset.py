"""Токен восстановления пароля через школьный email @547.team.

Поток:
1. /forgot-password (POST username) → ищем User, проверяем email @547.team,
   создаём PasswordResetToken (TTL 1 час), шлём письмо со ссылкой
   /reset-password/<raw_token> через Я.360 SMTP.
2. /reset-password/<token> (GET) рендерит форму нового пароля если токен валиден.
3. POST с новым паролем — set_password, помечаем used_at.

Хранится только sha256(token), сырой токен — лишь в письме. После использования
поле used_at !=NULL и токен инвалидируется.
"""
from datetime import datetime

from app.core.extensions import db


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_token"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    request_ip = db.Column(db.String(64), nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])
