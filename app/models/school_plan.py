from datetime import datetime

from app.core.extensions import db


class UserBuilding(db.Model):
    __tablename__ = 'user_building'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id'), nullable=False, index=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('building_links', lazy=True, cascade='all, delete-orphan'))
    building = db.relationship('Building', foreign_keys=[building_id])

    __table_args__ = (
        db.UniqueConstraint('user_id', 'building_id', name='uq_user_building_pair'),
    )


class SchoolPlanDirection(db.Model):
    __tablename__ = 'school_plan_direction'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    code = db.Column(db.String(50), nullable=True, unique=True)
    color = db.Column(db.String(20), nullable=True)
    text_color = db.Column(db.String(20), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<SchoolPlanDirection {self.name}>'


class SchoolPlanCategory(db.Model):
    __tablename__ = 'school_plan_category'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    code = db.Column(db.String(50), nullable=True, unique=True)
    color = db.Column(db.String(20), nullable=True)
    text_color = db.Column(db.String(20), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<SchoolPlanCategory {self.name}>'


class SchoolPlanEvent(db.Model):
    __tablename__ = 'school_plan_event'

    id = db.Column(db.Integer, primary_key=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_year.id'), nullable=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    short_title = db.Column(db.String(120), nullable=True)
    description = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.Date, nullable=False, index=True)
    end_date = db.Column(db.Date, nullable=True, index=True)
    period_type = db.Column(db.String(20), nullable=False, default='day')
    direction_id = db.Column(db.Integer, db.ForeignKey('school_plan_direction.id'), nullable=True, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('school_plan_category.id'), nullable=True, index=True)
    responsible_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    responsible_text = db.Column(db.String(255), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    participants = db.Column(db.String(500), nullable=True)
    priority = db.Column(db.String(20), nullable=False, default='normal', index=True)
    status = db.Column(db.String(20), nullable=False, default='planned', index=True)
    color = db.Column(db.String(20), nullable=True)
    text_color = db.Column(db.String(20), nullable=True)
    visibility_level = db.Column(db.String(20), nullable=False, default='school', index=True)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id'), nullable=True, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_class.id'), nullable=True, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)

    academic_year = db.relationship('AcademicYear', foreign_keys=[academic_year_id])
    direction = db.relationship('SchoolPlanDirection', foreign_keys=[direction_id])
    category = db.relationship('SchoolPlanCategory', foreign_keys=[category_id])
    responsible_user = db.relationship('User', foreign_keys=[responsible_user_id])
    building = db.relationship('Building', foreign_keys=[building_id])
    school_class = db.relationship('SchoolClass', foreign_keys=[class_id])
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    updated_by = db.relationship('User', foreign_keys=[updated_by_user_id])

    @property
    def display_title(self):
        return self.short_title or self.title

    @property
    def display_period(self):
        if self.end_date and self.end_date != self.start_date:
            return f'{self.start_date:%d.%m.%Y} — {self.end_date:%d.%m.%Y}'
        return f'{self.start_date:%d.%m.%Y}'

    @property
    def display_responsible(self):
        return self.responsible_text or (self.responsible_user.fio if self.responsible_user else '')

    @property
    def effective_color(self):
        return self.color or (self.direction.color if self.direction and self.direction.color else None) or (self.category.color if self.category and self.category.color else None) or '#3b82f6'

    @property
    def effective_text_color(self):
        return self.text_color or (self.direction.text_color if self.direction and self.direction.text_color else None) or (self.category.text_color if self.category and self.category.text_color else None) or '#ffffff'

    def __repr__(self):
        return f'<SchoolPlanEvent {self.title}>'
