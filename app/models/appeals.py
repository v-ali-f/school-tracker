from datetime import datetime

from app.core.extensions import db


class Appeal(db.Model):
    __tablename__ = 'appeal'

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(80), nullable=True, index=True)
    received_at = db.Column(db.Date, nullable=True, index=True)
    applicant_name = db.Column(db.String(255), nullable=False)
    applicant_contact = db.Column(db.String(255), nullable=True)
    channel = db.Column(db.String(80), nullable=True, index=True)
    subject = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    responsible_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    creator_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    linked_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True, index=True)
    deadline_at = db.Column(db.Date, nullable=True, index=True)
    status = db.Column(db.String(40), nullable=False, default='Новое', index=True)
    result_text = db.Column(db.Text, nullable=True)
    answered_at = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    responsible = db.relationship('User', foreign_keys=[responsible_user_id])
    creator = db.relationship('User', foreign_keys=[creator_user_id])
    linked_task = db.relationship('Task', foreign_keys=[linked_task_id])
    attachments = db.relationship('AppealAttachment', backref='appeal', lazy=True, cascade='all, delete-orphan')

    STATUS_CHOICES = ['Новое', 'В работе', 'На контроле', 'Подготовлен ответ', 'Закрыто', 'Просрочено']
    CHANNEL_CHOICES = ['Лично', 'Электронная почта', 'Телефон', 'Портал', 'Письмо', 'Иное']

    @property
    def is_overdue(self):
        if not self.deadline_at or self.status in {'Закрыто'}:
            return False
        return self.deadline_at < datetime.utcnow().date()


class AppealAttachment(db.Model):
    __tablename__ = 'appeal_attachment'

    id = db.Column(db.Integer, primary_key=True)
    appeal_id = db.Column(db.Integer, db.ForeignKey('appeal.id'), nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])
