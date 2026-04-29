from datetime import datetime

from app.core.extensions import db


class TaskType(db.Model):
    __tablename__ = 'task_type'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=100)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<TaskType {self.name}>'


class Task(db.Model):
    __tablename__ = 'task'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    task_type_id = db.Column(db.Integer, db.ForeignKey('task_type.id'), nullable=True, index=True)
    priority = db.Column(db.String(20), nullable=False, default='обычный', index=True)
    status = db.Column(db.String(40), nullable=False, default='Новая', index=True)

    creator_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    responsible_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    controller_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)

    child_id = db.Column(db.Integer, db.ForeignKey('child.id'), nullable=True, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_class.id'), nullable=True, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_year.id'), nullable=True, index=True)
    parent_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True, index=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id'), nullable=True, index=True)

    deadline_at = db.Column(db.DateTime, nullable=True, index=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    result_text = db.Column(db.Text, nullable=True)
    is_control_required = db.Column(db.Boolean, nullable=False, default=False)
    is_private = db.Column(db.Boolean, nullable=False, default=False)

    task_type = db.relationship('TaskType', backref=db.backref('tasks', lazy=True))
    creator = db.relationship('User', foreign_keys=[creator_user_id])
    responsible = db.relationship('User', foreign_keys=[responsible_user_id])
    controller = db.relationship('User', foreign_keys=[controller_user_id])
    child = db.relationship(
        'Child',
        foreign_keys=[child_id],
        backref=db.backref('tasks', lazy='dynamic', order_by='Task.created_at.desc()'),
    )
    incident = db.relationship(
        'Incident',
        foreign_keys=[incident_id],
        backref=db.backref('tasks', lazy='select', order_by='Task.created_at.desc()'),
    )
    school_class = db.relationship('SchoolClass', foreign_keys=[class_id])
    academic_year = db.relationship('AcademicYear', foreign_keys=[academic_year_id])
    comments = db.relationship('TaskComment', backref='task', lazy=True, cascade='all, delete-orphan', order_by='TaskComment.created_at.desc()')
    participants = db.relationship('TaskParticipant', backref='task', lazy=True, cascade='all, delete-orphan', order_by='TaskParticipant.id.asc()')
    checklist_items = db.relationship('TaskChecklistItem', backref='task', lazy=True, cascade='all, delete-orphan', order_by='TaskChecklistItem.sort_order.asc(), TaskChecklistItem.id.asc()')
    history_entries = db.relationship('TaskHistory', backref='task', lazy=True, cascade='all, delete-orphan', order_by='TaskHistory.created_at.desc()')
    parent_task = db.relationship('Task', remote_side=[id], backref=db.backref('subtasks', lazy=True, cascade='all'))

    STATUS_NEW = 'Новая'
    STATUS_IN_PROGRESS = 'В работе'
    STATUS_REVIEW = 'На проверке'
    STATUS_DONE = 'Выполнена'
    STATUS_REWORK = 'Возвращена на доработку'
    STATUS_WAITING = 'Ждет информации'
    STATUS_APPROVAL = 'На согласовании'
    STATUS_POSTPONED = 'Отложена'
    STATUS_CANCELLED = 'Отменена'
    STATUS_OVERDUE = 'Просрочена'
    STATUS_CLOSED = 'Закрыта'

    STATUS_CHOICES = [
        STATUS_NEW,
        STATUS_IN_PROGRESS,
        STATUS_REVIEW,
        STATUS_REWORK,
        STATUS_WAITING,
        STATUS_APPROVAL,
        STATUS_POSTPONED,
        STATUS_DONE,
        STATUS_CANCELLED,
        STATUS_CLOSED,
    ]

    ALLOWED_STATUS_TRANSITIONS = {
        STATUS_NEW: [STATUS_IN_PROGRESS, STATUS_WAITING, STATUS_POSTPONED, STATUS_CANCELLED],
        STATUS_IN_PROGRESS: [STATUS_REVIEW, STATUS_WAITING, STATUS_APPROVAL, STATUS_REWORK, STATUS_DONE, STATUS_POSTPONED, STATUS_CANCELLED],
        STATUS_REVIEW: [STATUS_DONE, STATUS_REWORK, STATUS_APPROVAL, STATUS_CANCELLED],
        STATUS_REWORK: [STATUS_IN_PROGRESS, STATUS_REVIEW, STATUS_WAITING, STATUS_CANCELLED],
        STATUS_WAITING: [STATUS_IN_PROGRESS, STATUS_POSTPONED, STATUS_CANCELLED],
        STATUS_APPROVAL: [STATUS_IN_PROGRESS, STATUS_DONE, STATUS_REWORK, STATUS_CANCELLED],
        STATUS_POSTPONED: [STATUS_IN_PROGRESS, STATUS_CANCELLED],
        STATUS_DONE: [STATUS_CLOSED, STATUS_REWORK],
        STATUS_CANCELLED: [],
        STATUS_CLOSED: [],
    }

    PRIORITY_CHOICES = ['низкий', 'обычный', 'высокий', 'срочный', 'критический']

    PARTICIPANT_ROLE_RESPONSIBLE = 'responsible'
    PARTICIPANT_ROLE_COEXECUTOR = 'coexecutor'
    PARTICIPANT_ROLE_OBSERVER = 'observer'
    PARTICIPANT_ROLE_CONTROLLER = 'controller'

    PARTICIPANT_ROLE_LABELS = {
        PARTICIPANT_ROLE_RESPONSIBLE: 'ответственный',
        PARTICIPANT_ROLE_COEXECUTOR: 'соисполнитель',
        PARTICIPANT_ROLE_OBSERVER: 'наблюдатель',
        PARTICIPANT_ROLE_CONTROLLER: 'контролирующий',
    }

    @property
    def is_overdue(self):
        if self.status in {self.STATUS_DONE, self.STATUS_CLOSED, self.STATUS_CANCELLED}:
            return False
        return bool(self.deadline_at and self.deadline_at < datetime.utcnow())

    @property
    def display_status(self):
        if self.is_overdue and self.status not in {self.STATUS_DONE, self.STATUS_CLOSED, self.STATUS_CANCELLED}:
            return self.STATUS_OVERDUE
        return self.status

    @property
    def checklist_total(self):
        return len(self.checklist_items or [])

    @property
    def checklist_done(self):
        return sum(1 for item in (self.checklist_items or []) if item.is_done)

    @property
    def checklist_percent(self):
        total = self.checklist_total
        if total <= 0:
            return 0
        return int(round((self.checklist_done / total) * 100))

    @property
    def participant_groups(self):
        groups = {key: [] for key in self.PARTICIPANT_ROLE_LABELS.keys()}
        for participant in self.participants or []:
            groups.setdefault(participant.role, []).append(participant)
        return groups

    def can_transition_to(self, new_status):
        if new_status == self.status:
            return True
        return new_status in self.ALLOWED_STATUS_TRANSITIONS.get(self.status, [])

    def __repr__(self):
        return f'<Task {self.id} {self.title}>'


class TaskParticipant(db.Model):
    __tablename__ = 'task_participant'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    role = db.Column(db.String(30), nullable=False, default=Task.PARTICIPANT_ROLE_COEXECUTOR, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])


class TaskHistory(db.Model):
    __tablename__ = 'task_history'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    field_name = db.Column(db.String(50), nullable=True)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    actor = db.relationship('User', foreign_keys=[actor_user_id])


class TaskChecklistItem(db.Model):
    __tablename__ = 'task_checklist_item'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    is_done = db.Column(db.Boolean, nullable=False, default=False, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=100)
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    completed_by = db.relationship('User', foreign_keys=[completed_by_user_id])


class TaskComment(db.Model):
    __tablename__ = 'task_comment'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, index=True)
    author_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    comment_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_system_comment = db.Column(db.Boolean, nullable=False, default=False)

    author = db.relationship('User', foreign_keys=[author_user_id])

    def __repr__(self):
        return f'<TaskComment {self.id} task={self.task_id}>'


class TaskTemplate(db.Model):
    __tablename__ = 'task_template'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    title_template = db.Column(db.String(255), nullable=False)
    description_template = db.Column(db.Text, nullable=True)
    task_type_id = db.Column(db.Integer, db.ForeignKey('task_type.id'), nullable=True, index=True)
    priority = db.Column(db.String(20), nullable=False, default='обычный')
    default_deadline_days = db.Column(db.Integer, nullable=True)
    is_control_required = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    task_type = db.relationship('TaskType', foreign_keys=[task_type_id])
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    checklist_items = db.relationship('TaskTemplateChecklistItem', backref='template', lazy=True, cascade='all, delete-orphan', order_by='TaskTemplateChecklistItem.sort_order.asc(), TaskTemplateChecklistItem.id.asc()')


class TaskTemplateChecklistItem(db.Model):
    __tablename__ = 'task_template_checklist_item'

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('task_template.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=100)


class TaskNotification(db.Model):
    __tablename__ = 'task_notification'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    notification_type = db.Column(db.String(50), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_important = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    read_at = db.Column(db.DateTime, nullable=True)

    task = db.relationship('Task', foreign_keys=[task_id])
    user = db.relationship('User', foreign_keys=[user_id])


class TaskAutoRule(db.Model):
    __tablename__ = 'task_auto_rule'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), nullable=False, unique=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)



class TaskEmailLog(db.Model):
    __tablename__ = 'task_email_log'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    notification_type = db.Column(db.String(50), nullable=False, index=True)
    email_to = db.Column(db.String(255), nullable=True)
    subject = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='pending', index=True)
    error_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    sent_at = db.Column(db.DateTime, nullable=True)

    task = db.relationship('Task', foreign_keys=[task_id])
    user = db.relationship('User', foreign_keys=[user_id])


class TaskAttachment(db.Model):
    __tablename__ = 'task_attachment'

    FILE_KIND_BASIS = 'basis'
    FILE_KIND_WORK = 'work'
    FILE_KIND_CHOICES = [FILE_KIND_BASIS, FILE_KIND_WORK]
    FILE_KIND_LABELS = {
        FILE_KIND_BASIS: 'Основание',
        FILE_KIND_WORK: 'Рабочий файл',
    }

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    content_type = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    file_kind = db.Column(db.String(20), nullable=False, default=FILE_KIND_WORK, index=True)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    task = db.relationship('Task', backref=db.backref('attachments', lazy=True, cascade='all, delete-orphan', order_by='TaskAttachment.created_at.desc()'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_user_id])

    @property
    def is_basis(self):
        return self.file_kind == self.FILE_KIND_BASIS

    @property
    def display_kind(self):
        return self.FILE_KIND_LABELS.get(self.file_kind, self.file_kind)

    @property
    def size_kb(self):
        return round((self.file_size or 0) / 1024, 1)

    @property
    def size_mb(self):
        return round((self.file_size or 0) / (1024 * 1024), 2)

    def __repr__(self):
        return f'<TaskAttachment {self.id} task={self.task_id} {self.filename}>'
