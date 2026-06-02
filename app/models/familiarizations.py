from __future__ import annotations
from datetime import datetime
from app.core.extensions import db

class Familiarization(db.Model):
    __tablename__ = "familiarization"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    deadline_at = db.Column(db.DateTime, nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="active", server_default="active")
    author_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    author = db.relationship("User", foreign_keys=[author_user_id])
    original_filename = db.Column(db.String(255), nullable=True)
    stored_filename = db.Column(db.String(255), nullable=True)
    content_type = db.Column(db.String(120), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    recipients = db.relationship("FamiliarizationRecipient", back_populates="familiarization", cascade="all, delete-orphan", lazy="selectin")

class FamiliarizationRecipient(db.Model):
    __tablename__ = "familiarization_recipient"
    id = db.Column(db.Integer, primary_key=True)
    familiarization_id = db.Column(db.Integer, db.ForeignKey("familiarization.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    acknowledged_at = db.Column(db.DateTime, nullable=True, index=True)
    familiarization = db.relationship("Familiarization", back_populates="recipients")
    user = db.relationship("User")
    __table_args__ = (db.UniqueConstraint("familiarization_id", "user_id", name="uq_familiarization_recipient_user"),)
    @property
    def is_acknowledged(self):
        return self.acknowledged_at is not None
