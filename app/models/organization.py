from datetime import datetime
from types import SimpleNamespace

from app.core.extensions import db


class OrganizationSettings(db.Model):
    __tablename__ = "organization_settings"

    id = db.Column(db.Integer, primary_key=True)
    parent_org_name = db.Column(db.String(255), nullable=True)
    full_name = db.Column(db.String(255), nullable=True)
    short_name = db.Column(db.String(255), nullable=True)
    legal_name = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    phone = db.Column(db.String(64), nullable=True)
    fax = db.Column(db.String(64), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    website = db.Column(db.String(255), nullable=True)
    okpo = db.Column(db.String(32), nullable=True)
    ogrn = db.Column(db.String(32), nullable=True)
    inn = db.Column(db.String(32), nullable=True)
    kpp = db.Column(db.String(32), nullable=True)
    director_name = db.Column(db.String(255), nullable=True)
    director_position = db.Column(db.String(255), nullable=True)
    logo_path = db.Column(db.String(500), nullable=True)
    emblem_path = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    olympiad_school_login = db.Column(db.String(80), nullable=True)
    olympiad_ekis_code = db.Column(db.String(80), nullable=True)
    olympiad_school_name = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def display_name(self):
        return self.short_name or self.full_name or self.legal_name or "Образовательная организация"

    @classmethod
    def empty(cls):
        return SimpleNamespace(
            id=None,
            parent_org_name="",
            full_name="",
            short_name="",
            legal_name="",
            city="",
            address="",
            postal_code="",
            phone="",
            fax="",
            email="",
            website="",
            okpo="",
            ogrn="",
            inn="",
            kpp="",
            director_name="",
            director_position="",
            logo_path=None,
            emblem_path=None,
            is_active=True,
            created_at=None,
            updated_at=None,
            display_name="Образовательная организация",
        )

    def __repr__(self):
        return f"<OrganizationSettings {self.display_name}>"


class SystemMailSettings(db.Model):
    __tablename__ = "system_mail_settings"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(64), nullable=True)
    smtp_host = db.Column(db.String(255), nullable=True)
    smtp_port = db.Column(db.Integer, nullable=True)
    smtp_username = db.Column(db.String(255), nullable=True)
    smtp_password = db.Column(db.String(255), nullable=True)
    sender_email = db.Column(db.String(255), nullable=True)
    use_ssl = db.Column(db.Boolean, nullable=False, default=False)
    use_tls = db.Column(db.Boolean, nullable=False, default=True)
    login_url = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    updated_by = db.relationship('User', foreign_keys=[updated_by_user_id])


class MailSettingsLog(db.Model):
    __tablename__ = "mail_settings_log"

    id = db.Column(db.Integer, primary_key=True)
    action_type = db.Column(db.String(50), nullable=False, index=True)
    recipient = db.Column(db.String(255), nullable=True)
    subject = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), nullable=True, index=True)
    error_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
