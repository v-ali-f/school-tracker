from datetime import datetime

from app.core.extensions import db


class MobilePushToken(db.Model):
    __tablename__ = "mobile_push_token"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    token = db.Column(db.Text, nullable=False, unique=True)
    platform = db.Column(db.String(20), nullable=False, default="android")
    device_id = db.Column(db.String(128), nullable=True)
    app_version = db.Column(db.String(40), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user = db.relationship("User", foreign_keys=[user_id])
