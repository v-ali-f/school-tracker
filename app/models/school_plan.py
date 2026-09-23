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
    start_time = db.Column(db.Time, nullable=True)
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
    responsible_links = db.relationship(
        'SchoolPlanEventResponsible',
        backref='event',
        lazy='select',
        cascade='all, delete-orphan',
        order_by='SchoolPlanEventResponsible.sort_order',
    )
    target_grade_links = db.relationship(
        'SchoolPlanEventGrade',
        backref='event',
        lazy='select',
        cascade='all, delete-orphan',
        order_by='SchoolPlanEventGrade.grade',
    )
    target_class_links = db.relationship(
        'SchoolPlanEventClass',
        backref='event',
        lazy='select',
        cascade='all, delete-orphan',
        order_by='SchoolPlanEventClass.sort_order',
    )
    group_links = db.relationship(
        'SchoolPlanEventGroup',
        backref='event',
        lazy='select',
        cascade='all, delete-orphan',
        order_by='SchoolPlanEventGroup.sort_order',
    )

    @property
    def display_title(self):
        return self.short_title or self.title

    @property
    def display_period(self):
        if self.end_date and self.end_date != self.start_date:
            return f'{self.start_date:%d.%m.%Y} — {self.end_date:%d.%m.%Y}'
        return f'{self.start_date:%d.%m.%Y}'

    @property
    def display_time(self):
        return self.start_time.strftime('%H:%M') if self.start_time else ''

    @property
    def display_schedule(self):
        if self.start_time:
            return f'{self.display_period} · {self.display_time}'
        return self.display_period

    @property
    def display_responsible(self):
        names = [
            link.label
            for link in self.group_links
            if link.purpose == 'responsible' and link.label
        ]
        names.extend(
            link.user.fio or link.user.username
            for link in self.responsible_links
            if link.user
        )
        if not names and self.responsible_user:
            names.append(self.responsible_user.fio or self.responsible_user.username)
        if self.responsible_text and self.responsible_text not in names:
            names.append(self.responsible_text)
        return '; '.join(names)

    @property
    def display_audience(self):
        labels = [
            link.label
            for link in self.group_links
            if link.purpose == 'audience' and link.label
        ]
        labels.extend(f'{link.grade}-е классы' for link in self.target_grade_links)
        labels.extend(
            link.school_class.name
            for link in self.target_class_links
            if link.school_class
        )
        if labels:
            return ', '.join(labels)
        if self.school_class:
            return self.school_class.name
        return 'Вся школа'

    @property
    def effective_color(self):
        return self.color or (self.direction.color if self.direction and self.direction.color else None) or (self.category.color if self.category and self.category.color else None) or '#3b82f6'

    @property
    def effective_text_color(self):
        return self.text_color or (self.direction.text_color if self.direction and self.direction.text_color else None) or (self.category.text_color if self.category and self.category.text_color else None) or '#ffffff'

    def __repr__(self):
        return f'<SchoolPlanEvent {self.title}>'


class SchoolPlanEventResponsible(db.Model):
    __tablename__ = 'school_plan_event_responsible'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey('school_plan_event.id', ondelete='CASCADE'),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='CASCADE'),
        nullable=False,
    )
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        db.UniqueConstraint('event_id', 'user_id', name='uq_school_plan_event_responsible'),
        db.Index('ix_sp_event_responsible_link_event', 'event_id'),
        db.Index('ix_sp_event_responsible_link_user', 'user_id'),
    )


class SchoolPlanEventGrade(db.Model):
    __tablename__ = 'school_plan_event_grade'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey('school_plan_event.id', ondelete='CASCADE'),
        nullable=False,
    )
    grade = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint('grade BETWEEN 1 AND 11', name='ck_school_plan_event_grade_range'),
        db.UniqueConstraint('event_id', 'grade', name='uq_school_plan_event_grade'),
        db.Index('ix_sp_event_grade_link_event', 'event_id'),
        db.Index('ix_sp_event_grade_link_grade', 'grade'),
    )


class SchoolPlanEventClass(db.Model):
    __tablename__ = 'school_plan_event_class'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey('school_plan_event.id', ondelete='CASCADE'),
        nullable=False,
    )
    class_id = db.Column(
        db.Integer,
        db.ForeignKey('school_class.id', ondelete='CASCADE'),
        nullable=False,
    )
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    school_class = db.relationship('SchoolClass', foreign_keys=[class_id])

    __table_args__ = (
        db.UniqueConstraint('event_id', 'class_id', name='uq_school_plan_event_class'),
        db.Index('ix_sp_event_class_link_event', 'event_id'),
        db.Index('ix_sp_event_class_link_class', 'class_id'),
    )


class SchoolPlanEventGroup(db.Model):
    __tablename__ = 'school_plan_event_group'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey('school_plan_event.id', ondelete='CASCADE'),
        nullable=False,
    )
    purpose = db.Column(db.String(20), nullable=False)
    group_type = db.Column(db.String(30), nullable=False)
    group_key = db.Column(db.String(80), nullable=False, default='')
    label = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @property
    def form_value(self):
        return f'{self.group_type}:{self.group_key}'

    __table_args__ = (
        db.CheckConstraint(
            "purpose IN ('audience', 'responsible')",
            name='ck_school_plan_event_group_purpose',
        ),
        db.UniqueConstraint(
            'event_id',
            'purpose',
            'group_type',
            'group_key',
            name='uq_school_plan_event_group',
        ),
        db.Index('ix_sp_event_group_link_event', 'event_id'),
        db.Index('ix_sp_event_group_purpose_type', 'purpose', 'group_type'),
    )


class SchoolPlanEditorAccess(db.Model):
    __tablename__ = 'school_plan_editor_access'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='CASCADE'),
        nullable=False,
    )
    granted_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=True,
    )
    is_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default='true',
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    granted_by = db.relationship('User', foreign_keys=[granted_by_user_id])

    __table_args__ = (
        db.UniqueConstraint(
            'user_id', name='uq_school_plan_editor_access_user'
        ),
        db.Index('ix_sp_editor_access_user', 'user_id'),
    )
