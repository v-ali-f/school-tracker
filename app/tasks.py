from datetime import datetime
from io import BytesIO
import os
import uuid
from pathlib import Path
from datetime import timedelta

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for, send_file
from flask_login import current_user, login_required
from openpyxl import Workbook
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

from app.core.extensions import db
from app.models import (
    AcademicYear,
    Child,
    ChildEnrollment,
    SchoolClass,
    User,
    Task,
    TaskChecklistItem,
    TaskComment,
    TaskAttachment,
    TaskHistory,
    TaskParticipant,
    TaskType,
    TaskTemplate,
    TaskTemplateChecklistItem,
    TaskNotification,
    TaskAutoRule,
    TaskEmailLog,
)
from app.services.task_notifications import is_important_notification, send_task_email, send_task_max_notification


tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


DEFAULT_TASK_TYPES = [
    'поручение',
    'задача по обучающемуся',
    'задача по классу',
    'задача по документам',
    'задача по сопровождению',
    'задача по посещаемости',
    'иное',
]

ALLOWED_ROLES_CREATE = {
    'ADMIN', 'DEPUTY_DIRECTOR', 'METHODIST', 'CLASS_TEACHER', 'TEACHER',
    'SPECIALIST', 'SOCIAL_PEDAGOGUE', 'LOGOPEDIST', 'PSYCHOLOGIST',
    'DEFECTOLOGIST', 'TUTOR', 'ASSISTANT', 'EDUCATOR', 'SENIOR_EDUCATOR',
    'SECRETARY_ACADEMIC'
}

ADMIN_ROLES = {'ADMIN', 'DEPUTY_DIRECTOR', 'METHODIST', 'DIRECTOR'}
QUICK_FILTERS = {
    'new': 'Новые',
    'week': 'На этой неделе',
    'review': 'Ждущие проверки',
    'rework': 'Возвращенные на доработку',
    'my_children': 'По моим детям',
    'my_class': 'По моему классу',
    'unlinked': 'Без привязки',
}

TASK_ATTACHMENT_ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'zip', 'txt'}
TASK_ATTACHMENT_MAX_FILE_SIZE = 30 * 1024 * 1024
TASK_ATTACHMENT_MAX_FILES = 10


def _task_attachments_root() -> str:
    upload_root = current_app.config.get('UPLOAD_FOLDER') or os.path.abspath(os.path.join('data', 'uploads'))
    path = os.path.join(upload_root, 'tasks')
    os.makedirs(path, exist_ok=True)
    return path


def _task_abs_path(stored_path: str | None) -> str:
    if not stored_path:
        return ''
    if os.path.isabs(stored_path):
        return stored_path
    return os.path.join(current_app.config.get('UPLOAD_FOLDER') or os.path.abspath(os.path.join('data', 'uploads')), stored_path)


def _task_attachment_count(task: Task) -> int:
    return sum(1 for x in (task.attachments or []) if not x.is_deleted)


def _allowed_task_attachment(filename: str) -> bool:
    ext = (Path(filename).suffix or '').lower().lstrip('.')
    return ext in TASK_ATTACHMENT_ALLOWED_EXTENSIONS


def _format_file_size(size: int | None) -> str:
    size = int(size or 0)
    if size >= 1024 * 1024:
        return f'{round(size / (1024 * 1024), 2)} МБ'
    if size >= 1024:
        return f'{round(size / 1024, 1)} КБ'
    return f'{size} Б'


def _can_delete_attachment(task: Task, attachment: TaskAttachment) -> bool:
    role = getattr(current_user, 'role', None)
    if role in ADMIN_ROLES:
        return True
    uid = getattr(current_user, 'id', None)
    return uid in {task.creator_user_id, attachment.uploaded_by_user_id}


def _attachment_groups(task: Task):
    basis = [x for x in (task.attachments or []) if not x.is_deleted and x.file_kind == TaskAttachment.FILE_KIND_BASIS]
    work = [x for x in (task.attachments or []) if not x.is_deleted and x.file_kind != TaskAttachment.FILE_KIND_BASIS]
    return {'basis': basis, 'work': work}


def _save_uploaded_attachments(task: Task, files, file_kind: str):
    files = [f for f in (files or []) if f and getattr(f, 'filename', '')]
    if not files:
        return []
    existing_count = _task_attachment_count(task)
    if existing_count + len(files) > TASK_ATTACHMENT_MAX_FILES:
        raise ValueError(f'У одной задачи можно хранить не более {TASK_ATTACHMENT_MAX_FILES} файлов.')

    saved = []
    task_dir = os.path.join(_task_attachments_root(), str(task.id))
    os.makedirs(task_dir, exist_ok=True)
    upload_root = current_app.config.get('UPLOAD_FOLDER') or os.path.abspath(os.path.join('data', 'uploads'))

    for storage in files:
        original_name = (storage.filename or '').strip()
        safe_name = secure_filename(original_name) or 'file'
        if not _allowed_task_attachment(safe_name):
            raise ValueError(f'Формат файла не поддерживается: {original_name}')

        storage.stream.seek(0, os.SEEK_END)
        size = storage.stream.tell()
        storage.stream.seek(0)
        if size > TASK_ATTACHMENT_MAX_FILE_SIZE:
            raise ValueError(f'Файл {original_name} превышает ограничение 30 МБ.')

        ext = (Path(safe_name).suffix or '').lower()
        stored_filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:12]}{ext}"
        abs_path = os.path.join(task_dir, stored_filename)
        storage.save(abs_path)
        rel_path = os.path.relpath(abs_path, upload_root)

        row = TaskAttachment(
            task_id=task.id,
            filename=original_name,
            stored_filename=stored_filename,
            file_path=rel_path,
            content_type=(storage.mimetype or None),
            file_size=size,
            file_kind=file_kind if file_kind in TaskAttachment.FILE_KIND_CHOICES else TaskAttachment.FILE_KIND_WORK,
            uploaded_by_user_id=current_user.id,
        )
        db.session.add(row)
        saved.append(row)
        _add_history(task, f'Прикреплен файл: {original_name}', event_type='attachment_added', new_value=original_name)

    if saved:
        _deliver_notifications(task, 'attachment_added', 'К задаче добавлен файл', f'По задаче «{task.title}» добавлены новые вложения.')
    return saved


def _handle_task_attachments_from_form(task: Task):
    basis_files = request.files.getlist('basis_files')
    work_files = request.files.getlist('work_files')
    saved = []
    saved.extend(_save_uploaded_attachments(task, basis_files, TaskAttachment.FILE_KIND_BASIS))
    saved.extend(_save_uploaded_attachments(task, work_files, TaskAttachment.FILE_KIND_WORK))
    return saved


def _ensure_defaults():
    changed = False
    for idx, name in enumerate(DEFAULT_TASK_TYPES, start=1):
        exists = TaskType.query.filter_by(name=name).first()
        if not exists:
            db.session.add(TaskType(name=name, sort_order=idx * 10, is_active=True))
            changed = True
    if changed:
        db.session.commit()


def _can_create_tasks():
    role = getattr(current_user, 'role', None)
    return role in ALLOWED_ROLES_CREATE or role in ADMIN_ROLES


def _is_task_participant(task: Task, uid: int | None):
    if not uid:
        return False
    if uid in {task.creator_user_id, task.responsible_user_id, task.controller_user_id}:
        return True
    return any(p.user_id == uid for p in (task.participants or []))


def _can_view_task(task: Task):
    role = getattr(current_user, 'role', None)
    if role in ADMIN_ROLES:
        return True
    return _is_task_participant(task, getattr(current_user, 'id', None))




def _can_delete_task(task: Task):
    role = getattr(current_user, 'role', None)
    if role in ADMIN_ROLES:
        return True
    uid = getattr(current_user, 'id', None)
    return uid == task.creator_user_id

def _can_edit_task(task: Task):
    role = getattr(current_user, 'role', None)
    if role in ADMIN_ROLES:
        return True
    uid = getattr(current_user, 'id', None)
    if uid in {task.creator_user_id, task.responsible_user_id, task.controller_user_id}:
        return True
    return any(p.user_id == uid and p.role in {Task.PARTICIPANT_ROLE_COEXECUTOR, Task.PARTICIPANT_ROLE_CONTROLLER} for p in (task.participants or []))


def _current_year():
    return AcademicYear.query.filter_by(is_current=True).first()


def _grades_for_year(year_id):
    rows = db.session.query(SchoolClass.grade).filter(
        SchoolClass.academic_year_id == year_id,
        SchoolClass.grade.isnot(None)
    ).distinct().order_by(SchoolClass.grade.asc()).all()
    return [row[0] for row in rows if row[0] is not None]


def _classes_for_grade(year_id, grade):
    q = SchoolClass.query.filter(SchoolClass.academic_year_id == year_id)
    if grade is not None:
        q = q.filter(SchoolClass.grade == grade)
    return q.order_by(SchoolClass.name.asc()).all()


def _children_for_class(year_id, class_id):
    if not class_id:
        return []
    ens = (
        ChildEnrollment.query
        .join(Child, ChildEnrollment.child_id == Child.id)
        .filter(
            ChildEnrollment.academic_year_id == year_id,
            ChildEnrollment.school_class_id == class_id,
            ChildEnrollment.ended_at.is_(None),
        )
        .order_by(Child.last_name.asc(), Child.first_name.asc(), Child.middle_name.asc())
        .all()
    )
    return [en.child for en in ens if en.child]


def _parse_deadline(raw: str):
    raw = (raw or '').strip()
    if not raw:
        return None

    # Новая форма передаёт только дату: YYYY-MM-DD.
    # Сохраняем как конец выбранного дня, чтобы задача не становилась
    # просроченной утром этой даты.
    try:
        if len(raw) == 10 and raw.count('-') == 2:
            dt = datetime.strptime(raw, '%Y-%m-%d')
            return dt.replace(hour=23, minute=59, second=0, microsecond=0)
    except Exception:
        pass

    # Оставляем поддержку старого формата с временем для совместимости.
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue

    return None


def _parse_checklist_items(form):
    items = []
    raw_items = form.getlist('checklist_title')
    for idx, title in enumerate(raw_items, start=1):
        title = (title or '').strip()
        if title:
            items.append({'title': title, 'sort_order': idx * 10})
    raw_block = (form.get('checklist_text') or '').strip()
    if raw_block:
        for row in raw_block.splitlines():
            row = row.strip(' -•\t')
            if row:
                items.append({'title': row, 'sort_order': (len(items) + 1) * 10})
    return items


def _participants_for_role(task, role):
    return [p for p in (task.participants or []) if p.role == role]


def _users_by_ids(ids):
    ids = [x for x in ids if x]
    if not ids:
        return []
    return User.query.filter(User.id.in_(ids)).all()


def _replace_participants(task, coexecutor_ids, observer_ids, controller_id=None):
    keep = []
    if controller_id:
        keep.append((controller_id, Task.PARTICIPANT_ROLE_CONTROLLER))
    for uid in coexecutor_ids:
        keep.append((uid, Task.PARTICIPANT_ROLE_COEXECUTOR))
    for uid in observer_ids:
        keep.append((uid, Task.PARTICIPANT_ROLE_OBSERVER))

    existing = {(p.user_id, p.role): p for p in (task.participants or [])}
    keep_keys = set(keep)
    for key, obj in list(existing.items()):
        if key not in keep_keys:
            db.session.delete(obj)
    for user_id, role in keep:
        if (user_id, role) not in existing:
            db.session.add(TaskParticipant(task=task, user_id=user_id, role=role))


def _add_history(task, message, event_type='update', field_name=None, old_value=None, new_value=None, actor_user_id=None):
    db.session.add(TaskHistory(
        task=task,
        actor_user_id=actor_user_id if actor_user_id is not None else getattr(current_user, 'id', None),
        event_type=event_type,
        field_name=field_name,
        old_value=None if old_value is None else str(old_value),
        new_value=None if new_value is None else str(new_value),
        message=message,
    ))


def _track_task_field_changes(task, old_data):
    checks = [
        ('status', 'Статус'),
        ('deadline_at', 'Срок'),
        ('responsible_user_id', 'Ответственный'),
        ('priority', 'Приоритет'),
        ('description', 'Описание'),
        ('child_id', 'Привязка к обучающемуся'),
        ('completed_at', 'Факт завершения'),
    ]
    for field_name, label in checks:
        old_value = old_data.get(field_name)
        new_value = getattr(task, field_name)
        if old_value != new_value:
            _add_history(task, f'{label} изменен', event_type='field_changed', field_name=field_name, old_value=old_value, new_value=new_value)


def _status_badge_class(status):
    mapping = {
        Task.STATUS_NEW: 'secondary',
        Task.STATUS_IN_PROGRESS: 'primary',
        Task.STATUS_REVIEW: 'warning',
        Task.STATUS_REWORK: 'danger',
        Task.STATUS_WAITING: 'info',
        Task.STATUS_APPROVAL: 'dark',
        Task.STATUS_POSTPONED: 'secondary',
        Task.STATUS_DONE: 'success',
        Task.STATUS_CANCELLED: 'secondary',
        Task.STATUS_CLOSED: 'success',
        Task.STATUS_OVERDUE: 'danger',
    }
    return mapping.get(status, 'secondary')


def _apply_filters(query):
    status = (request.args.get('status') or '').strip()
    task_type_id = request.args.get('task_type_id', type=int)
    responsible_user_id = request.args.get('responsible_user_id', type=int)
    creator_user_id = request.args.get('creator_user_id', type=int)
    controller_user_id = request.args.get('controller_user_id', type=int)
    participant_user_id = request.args.get('participant_user_id', type=int)
    observer_user_id = request.args.get('observer_user_id', type=int)
    priority = (request.args.get('priority') or '').strip()
    child_id = request.args.get('child_id', type=int)
    class_id = request.args.get('class_id', type=int)
    academic_year_id = request.args.get('academic_year_id', type=int)
    created_date = (request.args.get('created_date') or '').strip()
    q = (request.args.get('q') or '').strip()
    overdue_only = request.args.get('overdue') == '1'
    quick = (request.args.get('quick') or '').strip()

    if status:
        if status == Task.STATUS_OVERDUE:
            query = query.filter(Task.status.notin_([Task.STATUS_DONE, Task.STATUS_CLOSED, Task.STATUS_CANCELLED]), Task.deadline_at.isnot(None), Task.deadline_at < datetime.utcnow())
        else:
            query = query.filter(Task.status == status)
    if task_type_id:
        query = query.filter(Task.task_type_id == task_type_id)
    if responsible_user_id:
        query = query.filter(Task.responsible_user_id == responsible_user_id)
    if creator_user_id:
        query = query.filter(Task.creator_user_id == creator_user_id)
    if controller_user_id:
        query = query.filter(Task.controller_user_id == controller_user_id)
    if participant_user_id:
        participant_task_ids = db.session.query(TaskParticipant.task_id).filter(
            TaskParticipant.user_id == participant_user_id,
            TaskParticipant.role == Task.PARTICIPANT_ROLE_COEXECUTOR,
        )
        query = query.filter(Task.id.in_(participant_task_ids))
    if observer_user_id:
        observer_task_ids = db.session.query(TaskParticipant.task_id).filter(
            TaskParticipant.user_id == observer_user_id,
            TaskParticipant.role == Task.PARTICIPANT_ROLE_OBSERVER,
        )
        query = query.filter(Task.id.in_(observer_task_ids))
    if priority:
        query = query.filter(Task.priority == priority)
    if child_id:
        query = query.filter(Task.child_id == child_id)
    if class_id:
        query = query.filter(Task.class_id == class_id)
    if academic_year_id:
        query = query.filter(Task.academic_year_id == academic_year_id)
    if created_date:
        query = query.filter(func.date(Task.created_at) == created_date)
    if q:
        like = f'%{q}%'
        query = query.filter(or_(Task.title.ilike(like), Task.description.ilike(like), Task.result_text.ilike(like)))
    if overdue_only:
        query = query.filter(Task.status.notin_([Task.STATUS_DONE, Task.STATUS_CLOSED, Task.STATUS_CANCELLED]), Task.deadline_at.isnot(None), Task.deadline_at < datetime.utcnow())

    uid = getattr(current_user, 'id', None)
    if quick == 'new':
        query = query.filter(Task.status == Task.STATUS_NEW)
    elif quick == 'week':
        query = query.filter(Task.deadline_at.isnot(None), func.date(Task.deadline_at) <= datetime.utcnow().date())
    elif quick == 'review':
        query = query.filter(Task.status == Task.STATUS_REVIEW)
    elif quick == 'rework':
        query = query.filter(Task.status == Task.STATUS_REWORK)
    elif quick == 'unlinked':
        query = query.filter(Task.child_id.is_(None), Task.class_id.is_(None))
    elif quick == 'my_children' and uid:
        query = query.filter(Task.creator_user_id == uid, Task.child_id.isnot(None))
    elif quick == 'my_class' and uid:
        query = query.filter(Task.creator_user_id == uid, Task.class_id.isnot(None))

    return query


def _common_filter_context():
    users = User.query.filter(User.is_active_user.is_(True)).order_by(User.last_name.asc(), User.first_name.asc()).all()
    return {
        'task_types': TaskType.query.filter_by(is_active=True).order_by(TaskType.sort_order.asc(), TaskType.name.asc()).all(),
        'users': users,
        'status_choices': Task.STATUS_CHOICES,
        'priority_choices': Task.PRIORITY_CHOICES,
        'quick_filters': QUICK_FILTERS,
        'status_badge_class': _status_badge_class,
        'participant_role_labels': Task.PARTICIPANT_ROLE_LABELS,
        'years': AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all(),
    }



def _task_scope_query(scope='my'):
    uid = getattr(current_user, 'id', None)
    role = getattr(current_user, 'role', None)
    if scope == 'created':
        return Task.query.filter(Task.creator_user_id == uid)
    if scope == 'overdue':
        query = Task.query
        if role not in ADMIN_ROLES:
            query = query.filter(
                or_(
                    Task.creator_user_id == uid,
                    Task.responsible_user_id == uid,
                    Task.controller_user_id == uid,
                    Task.id.in_(db.session.query(TaskParticipant.task_id).filter(TaskParticipant.user_id == uid))
                )
            )
        return query.filter(
            Task.status.notin_([Task.STATUS_DONE, Task.STATUS_CLOSED, Task.STATUS_CANCELLED]),
            Task.deadline_at.isnot(None),
            Task.deadline_at < datetime.utcnow(),
        )
    if scope == 'all' and role in ADMIN_ROLES:
        return Task.query
    return Task.query.filter(
        or_(
            Task.responsible_user_id == uid,
            Task.controller_user_id == uid,
            Task.creator_user_id == uid,
            Task.id.in_(db.session.query(TaskParticipant.task_id).filter(TaskParticipant.user_id == uid))
        )
    )


def _ordered_task_rows(query):
    return query.order_by(Task.deadline_at.is_(None), Task.deadline_at.asc(), Task.created_at.desc()).all()


def _build_tasks_workbook(tasks, title='Задачи'):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Задачи'
    ws.append([
        '№', 'Задача', 'Тип', 'Статус', 'Приоритет', 'Ответственный', 'Постановщик',
        'Контролирующий', 'Класс', 'Обучающийся', 'Срок', 'Создана', 'Завершена',
        'Чек-лист %', 'Приватная', 'Контроль', 'Результат'
    ])
    for idx, task in enumerate(tasks, start=1):
        ws.append([
            idx,
            task.title,
            task.task_type.name if task.task_type else '',
            task.display_status,
            task.priority,
            task.responsible.fio if task.responsible and task.responsible.fio else (task.responsible.username if task.responsible else ''),
            task.creator.fio if task.creator and task.creator.fio else (task.creator.username if task.creator else ''),
            task.controller.fio if task.controller and task.controller.fio else (task.controller.username if task.controller else ''),
            task.school_class.name if task.school_class else '',
            task.child.fio if task.child else '',
            task.deadline_at.strftime('%d.%m.%Y %H:%M') if task.deadline_at else '',
            task.created_at.strftime('%d.%m.%Y %H:%M') if task.created_at else '',
            task.completed_at.strftime('%d.%m.%Y %H:%M') if task.completed_at else '',
            task.checklist_percent,
            'Да' if task.is_private else 'Нет',
            'Да' if task.is_control_required else 'Нет',
            task.result_text or '',
        ])
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 2, 12), 40)
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


def _task_analytics_context(base_query):
    rows = _ordered_task_rows(base_query)
    active_statuses = {Task.STATUS_NEW, Task.STATUS_IN_PROGRESS, Task.STATUS_REVIEW, Task.STATUS_REWORK, Task.STATUS_WAITING, Task.STATUS_APPROVAL, Task.STATUS_POSTPONED}
    active_count = sum(1 for t in rows if t.status in active_statuses and not t.is_overdue)
    overdue_count = sum(1 for t in rows if t.is_overdue)
    review_count = sum(1 for t in rows if t.status == Task.STATUS_REVIEW)
    done_rows = [t for t in rows if t.completed_at]
    durations = []
    on_time = 0
    for task in done_rows:
        if task.created_at and task.completed_at:
            durations.append((task.completed_at - task.created_at).total_seconds() / 86400)
        if not task.deadline_at or task.completed_at <= task.deadline_at:
            on_time += 1
    by_status = sorted([(status, sum(1 for t in rows if t.display_status == status)) for status in sorted({t.display_status for t in rows})], key=lambda x: x[0])
    by_executor = sorted([(name, count) for name, count in {((t.responsible.fio if t.responsible and t.responsible.fio else (t.responsible.username if t.responsible else '—'))): sum(1 for x in rows if ((x.responsible.fio if x.responsible and x.responsible.fio else (x.responsible.username if x.responsible else '—')) == (t.responsible.fio if t.responsible and t.responsible.fio else (t.responsible.username if t.responsible else '—')))) for t in rows}.items()], key=lambda x: (-x[1], x[0]))[:15]
    by_type = sorted([(name, count) for name, count in {((t.task_type.name if t.task_type else '—')): sum(1 for x in rows if (x.task_type.name if x.task_type else '—') == (t.task_type.name if t.task_type else '—')) for t in rows}.items()], key=lambda x: (-x[1], x[0]))
    by_class = sorted([(name, count) for name, count in {((t.school_class.name if t.school_class else 'Без класса')): sum(1 for x in rows if (x.school_class.name if x.school_class else 'Без класса') == (t.school_class.name if t.school_class else 'Без класса')) for t in rows}.items()], key=lambda x: (-x[1], x[0]))[:15]
    by_child = sorted([(name, count) for name, count in {((t.child.fio if t.child else 'Без привязки')): sum(1 for x in rows if (x.child.fio if x.child else 'Без привязки') == (t.child.fio if t.child else 'Без привязки')) for t in rows}.items()], key=lambda x: (-x[1], x[0]))[:15]
    return {
        'rows': rows,
        'active_count': active_count,
        'overdue_count': overdue_count,
        'review_count': review_count,
        'done_count': len(done_rows),
        'avg_days': round(sum(durations) / len(durations), 1) if durations else 0,
        'on_time_percent': round((on_time / len(done_rows)) * 100, 1) if done_rows else 0,
        'by_status': by_status,
        'by_executor': by_executor,
        'by_type': by_type,
        'by_class': by_class,
        'by_child': by_child,
    }



def _user_notifications_enabled(user, is_important=False):
    if not user or not getattr(user, 'is_active_user', False):
        return False
    if getattr(user, 'task_notifications_enabled', True) is False:
        return False
    if is_important and getattr(user, 'task_notify_only_important', False):
        return True
    if (not is_important) and getattr(user, 'task_notify_only_important', False):
        return False
    return True


def _email_enabled_for_user(user, is_important=False):
    if not user or not getattr(user, 'email', None):
        return False
    if getattr(user, 'task_email_enabled', False) is not True:
        return False
    if (not is_important) and getattr(user, 'task_notify_only_important', False):
        return False
    return True


def _get_notification_recipients(task, notification_type, extra_user_ids=None):
    user_ids = {task.responsible_user_id, task.controller_user_id, task.creator_user_id}
    for participant in task.participants or []:
        user_ids.add(participant.user_id)
    for user_id in extra_user_ids or []:
        if user_id:
            user_ids.add(user_id)
    user_ids.discard(None)
    actor_id = getattr(current_user, 'id', None)
    if actor_id and notification_type not in {'overdue', 'auto_created'}:
        # Не присылаем уведомление автору действия, если он не является адресатом задачи.
        # Но если человек сам себе поставил задачу или сам является ответственным/
        # контролёром/участником, уведомление должно прийти.
        is_actor_task_recipient = (
            actor_id == task.responsible_user_id
            or actor_id == task.controller_user_id
            or any(getattr(p, 'user_id', None) == actor_id for p in (task.participants or []))
        )
        if not is_actor_task_recipient:
            user_ids.discard(actor_id)
    if not user_ids:
        return []
    return User.query.filter(User.id.in_(list(user_ids))).all()


_TASK_NOTIFY_EVENT_CLASS = {
    'new_task': 'open',
    'auto_created': 'open',
    'status_changed': 'status',
    'sent_to_review': 'status',
    'returned_for_rework': 'status',
    'deadline_changed': 'status',
    'overdue': 'status',
    'closed': 'close',
    'attachment_added': 'note',
    'comment_added': 'note',
    'task_updated': 'note',
}
_TASK_NOTIFY_MODE_ALLOWED = {
    'all': {'open', 'status', 'close', 'note'},
    'status': {'status', 'close'},
    'open_close': {'open', 'close'},
    'close_only': {'close'},
}


def _task_mode_allows(user, notification_type):
    mode = (getattr(user, 'notify_task_mode', None) or 'all').strip() or 'all'
    if mode == 'all':
        return True
    ev = _TASK_NOTIFY_EVENT_CLASS.get(notification_type)
    if ev is None:
        return True
    allowed = _TASK_NOTIFY_MODE_ALLOWED.get(mode, _TASK_NOTIFY_MODE_ALLOWED['all'])
    return ev in allowed


def _deliver_notifications(task, notification_type, title, message, extra_user_ids=None):
    is_important = is_important_notification(notification_type)
    recipients = _get_notification_recipients(task, notification_type, extra_user_ids=extra_user_ids)
    for user in recipients:
        if not _task_mode_allows(user, notification_type):
            continue
        if _user_notifications_enabled(user, is_important=is_important):
            db.session.add(TaskNotification(
                task_id=task.id,
                user_id=user.id,
                notification_type=notification_type,
                title=title,
                message=message,
                is_important=is_important,
            ))
            try:
                send_task_max_notification(task, user, notification_type, title, message)
            except Exception:
                current_app.logger.exception(
                    'Failed to send task MAX notification for task_id=%s user_id=%s',
                    task.id,
                    user.id,
                )
        if _email_enabled_for_user(user, is_important=is_important):
            try:
                current_app.logger.info(
                    'Task email send attempt: task_id=%s user_id=%s email=%s type=%s',
                    task.id,
                    user.id,
                    user.email,
                    notification_type,
                )
                send_task_email(task, user, notification_type, title, message)
            except Exception:
                current_app.logger.exception(
                    'Failed to queue task email for task_id=%s user_id=%s',
                    task.id,
                    user.id,
                )
        else:
            current_app.logger.info(
                'Task email skipped: task_id=%s user_id=%s email=%s email_enabled=%s only_important=%s important=%s',
                task.id,
                getattr(user, 'id', None),
                getattr(user, 'email', None),
                getattr(user, 'task_email_enabled', None),
                getattr(user, 'task_notify_only_important', None),
                is_important,
            )


def _delete_task_related_data(task: Task):
    child_tasks = Task.query.filter_by(parent_task_id=task.id).all()
    for child_task in child_tasks:
        _delete_task_related_data(child_task)
        db.session.delete(child_task)

    TaskNotification.query.filter_by(task_id=task.id).delete(synchronize_session=False)
    TaskParticipant.query.filter_by(task_id=task.id).delete(synchronize_session=False)
    TaskChecklistItem.query.filter_by(task_id=task.id).delete(synchronize_session=False)
    TaskComment.query.filter_by(task_id=task.id).delete(synchronize_session=False)
    TaskHistory.query.filter_by(task_id=task.id).delete(synchronize_session=False)
    TaskEmailLog.query.filter_by(task_id=task.id).delete(synchronize_session=False)

    attachments = TaskAttachment.query.filter_by(task_id=task.id).all()
    for attachment in attachments:
        file_path = getattr(attachment, 'file_path', None)
        abs_path = _task_abs_path(file_path) if file_path else None
        if abs_path and os.path.exists(abs_path):
            try:
                os.remove(abs_path)
            except Exception:
                current_app.logger.exception(
                    'Не удалось удалить файл вложения задачи %s',
                    getattr(attachment, 'id', None)
                )
        db.session.delete(attachment)


def _ensure_overdue_notifications_for_user(user_id):
    if not user_id:
        return
    overdue_tasks = _task_scope_query('my').filter(
        Task.status.notin_([Task.STATUS_DONE, Task.STATUS_CLOSED, Task.STATUS_CANCELLED]),
        Task.deadline_at.isnot(None),
        Task.deadline_at < datetime.utcnow()
    ).all()
    for task in overdue_tasks:
        exists = TaskNotification.query.filter_by(task_id=task.id, user_id=user_id, notification_type='overdue').first()
        if exists:
            continue
        db.session.add(TaskNotification(
            task_id=task.id,
            user_id=user_id,
            notification_type='overdue',
            title='Просрочена задача',
            message=f'Задача «{task.title}» стала просроченной.',
            is_important=True,
        ))
        user = User.query.get(user_id)
        if _email_enabled_for_user(user, is_important=True):
            try:
                send_task_email(task, user, 'overdue', 'Просрочена задача', f'Задача «{task.title}» стала просроченной.')
            except Exception:
                current_app.logger.exception('Failed to send overdue task email')


def _notification_payload(row):
    return {
        'id': row.id,
        'task_id': row.task_id,
        'title': row.title,
        'message': row.message,
        'notification_type': row.notification_type,
        'is_read': bool(row.is_read),
        'is_important': bool(getattr(row, 'is_important', False)),
        'created_at': row.created_at.strftime('%d.%m.%Y %H:%M') if row.created_at else '',
        'task_url': url_for('tasks.task_card', task_id=row.task_id),
    }


def _apply_template_defaults(template, form_data):
    if not template:
        return form_data
    result = dict(form_data)
    result.setdefault('title', template.title_template or '')
    result.setdefault('description', template.description_template or '')
    result.setdefault('task_type_id', template.task_type_id)
    result.setdefault('priority', template.priority or 'обычный')
    if template.default_deadline_days and not result.get('deadline_at'):
        result['deadline_at'] = (datetime.utcnow() + timedelta(days=template.default_deadline_days)).strftime('%Y-%m-%dT%H:%M')
    result.setdefault('is_control_required', '1' if template.is_control_required else '')
    result.setdefault('checklist_text', '\n'.join(item.title for item in (template.checklist_items or [])))
    return result


def _save_template_checklist(template, raw_text):
    for item in list(template.checklist_items):
        db.session.delete(item)
    rows = []
    for idx, row in enumerate((raw_text or '').splitlines(), start=1):
        row = row.strip(' -•\t')
        if row:
            rows.append(TaskTemplateChecklistItem(template=template, title=row, sort_order=idx * 10))
    for item in rows:
        db.session.add(item)


def _bootstrap_auto_rules():
    defaults = {
        'incident_created': 'Автозадача по новому инциденту',
        'document_overdue': 'Автозадача по просроченному документу',
    }
    changed = False
    for code, name in defaults.items():
        if not TaskAutoRule.query.filter_by(code=code).first():
            db.session.add(TaskAutoRule(code=code, name=name, is_enabled=True))
            changed = True
    if changed:
        db.session.commit()


def _task_counts():
    uid = getattr(current_user, 'id', None)
    base_my = Task.query.filter(
        or_(
            Task.responsible_user_id == uid,
            Task.controller_user_id == uid,
            Task.id.in_(db.session.query(TaskParticipant.task_id).filter(TaskParticipant.user_id == uid))
        )
    )
    base_all = Task.query
    return {
        'my_total': base_my.count(),
        'my_overdue': base_my.filter(Task.status.notin_([Task.STATUS_DONE, Task.STATUS_CLOSED, Task.STATUS_CANCELLED]), Task.deadline_at.isnot(None), Task.deadline_at < datetime.utcnow()).count(),
        'my_today': base_my.filter(Task.deadline_at.isnot(None), db.func.date(Task.deadline_at) == datetime.utcnow().date()).count(),
        'my_review': base_my.filter(Task.status == Task.STATUS_REVIEW).count(),
        'my_rework': base_my.filter(Task.status == Task.STATUS_REWORK).count(),
        'status_rows': (
            base_all.with_entities(Task.status, func.count(Task.id))
            .group_by(Task.status)
            .order_by(Task.status.asc())
            .all()
        ),
        'unread_notifications': TaskNotification.query.filter_by(user_id=uid, is_read=False).count(),
    }


def _save_checklist(task, form):
    new_items = _parse_checklist_items(form)
    existing_map = {item.id: item for item in task.checklist_items}
    keep_ids = set()
    for idx, item_id_raw in enumerate(form.getlist('existing_checklist_id')):
        item_id = int(item_id_raw) if item_id_raw and str(item_id_raw).isdigit() else None
        title = (form.getlist('existing_checklist_title')[idx] or '').strip() if idx < len(form.getlist('existing_checklist_title')) else ''
        is_done = idx < len(form.getlist('existing_checklist_done_flags')) and form.getlist('existing_checklist_done_flags')[idx] == '1'
        obj = existing_map.get(item_id)
        if not obj:
            continue
        keep_ids.add(obj.id)
        old_done = obj.is_done
        obj.title = title or obj.title
        obj.sort_order = (idx + 1) * 10
        obj.is_done = is_done
        if obj.is_done and not old_done:
            obj.completed_at = datetime.utcnow()
            obj.completed_by_user_id = current_user.id
            _add_history(task, f'Отмечен пункт чек-листа: {obj.title}', event_type='checklist_done')
        elif old_done and not obj.is_done:
            obj.completed_at = None
            obj.completed_by_user_id = None
            _add_history(task, f'Снят флаг выполнения пункта чек-листа: {obj.title}', event_type='checklist_reopen')
    for obj in list(task.checklist_items):
        if obj.id not in keep_ids:
            db.session.delete(obj)
    for item in new_items:
        db.session.add(TaskChecklistItem(task=task, title=item['title'], sort_order=item['sort_order']))
        _add_history(task, f'Добавлен пункт чек-листа: {item["title"]}', event_type='checklist_add')


@tasks_bp.before_app_request
def _bootstrap_task_types():
    try:
        _ensure_defaults()
        _bootstrap_auto_rules()
        if getattr(current_user, 'is_authenticated', False):
            _ensure_overdue_notifications_for_user(current_user.id)
            db.session.commit()
    except Exception:
        db.session.rollback()


@tasks_bp.app_context_processor
def _tasks_context_processor():
    return {
        'task_status_badge_class': _status_badge_class,
        'task_participant_role_labels': Task.PARTICIPANT_ROLE_LABELS,
        'now': datetime.utcnow,
    }


@tasks_bp.route('/')
@login_required
def index():
    return redirect(url_for('tasks.my_tasks'))


@tasks_bp.route('/my')
@login_required
def my_tasks():
    query = _apply_filters(_task_scope_query('my'))
    tasks = _ordered_task_rows(query)
    return render_template('tasks/list.html', title='Мои задачи', tasks=tasks, list_kind='my', counts=_task_counts(), **_common_filter_context())


@tasks_bp.route('/created')
@login_required
def created_by_me():
    query = _apply_filters(_task_scope_query('created'))
    tasks = query.order_by(Task.created_at.desc()).all()
    return render_template('tasks/list.html', title='Поставленные мной', tasks=tasks, list_kind='created', counts=_task_counts(), **_common_filter_context())


@tasks_bp.route('/overdue')
@login_required
def overdue_tasks():
    query = _apply_filters(_task_scope_query('overdue'))
    tasks = query.order_by(Task.deadline_at.asc(), Task.created_at.desc()).all()
    return render_template('tasks/list.html', title='Просроченные задачи', tasks=tasks, list_kind='overdue', counts=_task_counts(), **_common_filter_context())


@tasks_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_task():
    if not _can_create_tasks():
        abort(403)

    template_id = request.form.get('template_id', type=int) if request.method == 'POST' else request.args.get('template_id', type=int)
    selected_template = TaskTemplate.query.get(template_id) if template_id else None
    current_year = _current_year()
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    selected_year_id = request.form.get('academic_year_id', type=int) if request.method == 'POST' else request.args.get('academic_year_id', type=int)
    if not selected_year_id and current_year:
        selected_year_id = current_year.id
    selected_grade = request.form.get('grade', type=int) if request.method == 'POST' else request.args.get('grade', type=int)
    selected_class_id = request.form.get('class_id', type=int) if request.method == 'POST' else request.args.get('class_id', type=int)
    selected_child_id = request.form.get('child_id', type=int) if request.method == 'POST' else request.args.get('child_id', type=int)
    parent_task_id = request.form.get('parent_task_id', type=int) if request.method == 'POST' else request.args.get('parent_task_id', type=int)

    grades = _grades_for_year(selected_year_id) if selected_year_id else []
    classes = _classes_for_grade(selected_year_id, selected_grade) if selected_year_id else []
    children = _children_for_class(selected_year_id, selected_class_id) if selected_year_id and selected_class_id else []

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip() or None
        task_type_id = request.form.get('task_type_id', type=int)
        priority = (request.form.get('priority') or 'обычный').strip()
        responsible_user_id = request.form.get('responsible_user_id', type=int)
        controller_user_id = request.form.get('controller_user_id', type=int)
        child_id = request.form.get('child_id', type=int)
        deadline_at = _parse_deadline(request.form.get('deadline_at'))
        is_control_required = bool(request.form.get('is_control_required'))
        is_private = bool(request.form.get('is_private'))
        coexecutor_ids = [int(x) for x in request.form.getlist('coexecutor_user_ids') if str(x).isdigit()]
        observer_ids = [int(x) for x in request.form.getlist('observer_user_ids') if str(x).isdigit()]

        if not title:
            flash('Укажите название задачи', 'danger')
        elif not responsible_user_id:
            flash('Укажите ответственного', 'danger')
        else:
            task = Task(
                title=title,
                description=description,
                task_type_id=task_type_id or None,
                priority=priority if priority in Task.PRIORITY_CHOICES else 'обычный',
                status=Task.STATUS_NEW,
                creator_user_id=current_user.id,
                responsible_user_id=responsible_user_id,
                controller_user_id=controller_user_id or None,
                child_id=child_id or None,
                class_id=selected_class_id or None,
                academic_year_id=selected_year_id or None,
                deadline_at=deadline_at,
                is_control_required=is_control_required,
                is_private=is_private,
                parent_task_id=parent_task_id or None,
            )
            db.session.add(task)
            db.session.flush()
            _replace_participants(task, coexecutor_ids=coexecutor_ids, observer_ids=observer_ids, controller_id=controller_user_id)
            _save_checklist(task, request.form)
            try:
                _handle_task_attachments_from_form(task)
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), 'danger')
                return render_template('tasks/form.html',
                                       title='Новая задача',
                                       task=None,
                                       parent_task=Task.query.get(parent_task_id) if parent_task_id else None,
                                       template_defaults=_apply_template_defaults(selected_template, {}) if selected_template else {},
                                       selected_template=selected_template,
                                       grades=grades,
                                       classes=classes,
                                       children=children,
                                       selected_year_id=selected_year_id,
                                       selected_grade=selected_grade,
                                       selected_class_id=selected_class_id,
                                       selected_child_id=selected_child_id,
                                       **_common_filter_context())
            _add_history(task, 'Задача создана', event_type='created')
            _deliver_notifications(task, 'new_task', 'Новая задача', f'Вам назначена задача «{task.title}».')
            if parent_task_id:
                _add_history(task, f'Создана как подзадача к задаче №{parent_task_id}', event_type='subtask_created')
            db.session.commit()
            flash('Задача создана', 'success')
            return redirect(url_for('tasks.task_card', task_id=task.id))

    parent_task = Task.query.get(parent_task_id) if parent_task_id else None
    template_defaults = _apply_template_defaults(selected_template, {}) if selected_template else {}
    return render_template('tasks/form.html',
                           title='Новая задача',
                           task=None,
                           parent_task=parent_task,
                           template_defaults=template_defaults,
                           selected_template=selected_template,
                           grades=grades,
                           classes=classes,
                           children=children,
                           selected_year_id=selected_year_id,
                           selected_grade=selected_grade,
                           selected_class_id=selected_class_id,
                           selected_child_id=selected_child_id,
                           **_common_filter_context())




@tasks_bp.route('/archive')
@login_required
def archive_tasks():
    query = _task_scope_query('all' if getattr(current_user, 'role', None) in ADMIN_ROLES else 'my').filter(
        Task.status.in_([Task.STATUS_DONE, Task.STATUS_CLOSED, Task.STATUS_CANCELLED])
    )
    query = _apply_filters(query)
    tasks = query.order_by(Task.completed_at.desc().nullslast(), Task.updated_at.desc()).all()
    return render_template('tasks/list.html', title='Архив задач', tasks=tasks, list_kind='archive', counts=_task_counts(), **_common_filter_context())


@tasks_bp.route('/notifications')
@login_required
def notifications():
    rows_query = TaskNotification.query.filter_by(user_id=current_user.id)
    unread = (request.args.get('unread') or '').strip()
    notification_type = (request.args.get('notification_type') or '').strip()
    q = (request.args.get('q') or '').strip()
    if unread == '1':
        rows_query = rows_query.filter(TaskNotification.is_read.is_(False))
    elif unread == '0':
        rows_query = rows_query.filter(TaskNotification.is_read.is_(True))
    if notification_type:
        rows_query = rows_query.filter(TaskNotification.notification_type == notification_type)
    if q:
        rows_query = rows_query.filter(or_(TaskNotification.title.ilike(f'%{q}%'), TaskNotification.message.ilike(f'%{q}%')))
    rows = rows_query.order_by(TaskNotification.created_at.desc()).limit(300).all()
    notification_types = [x[0] for x in db.session.query(TaskNotification.notification_type).filter_by(user_id=current_user.id).distinct().order_by(TaskNotification.notification_type.asc()).all()]
    return render_template('tasks/notifications.html', title='Уведомления по задачам', notifications=rows, counts=_task_counts(), notification_types=notification_types)


@tasks_bp.route('/notifications/feed')
@login_required
def notifications_feed():
    latest = TaskNotification.query.filter_by(user_id=current_user.id).order_by(TaskNotification.created_at.desc()).limit(10).all()
    unread_count = TaskNotification.query.filter_by(user_id=current_user.id, is_read=False).count()
    latest_unread = TaskNotification.query.filter_by(user_id=current_user.id, is_read=False).order_by(TaskNotification.created_at.desc()).first()
    return jsonify({
        'unread_count': unread_count,
        'items': [_notification_payload(x) for x in latest],
        'play_sound': bool(latest_unread and not latest_unread.is_read and getattr(current_user, 'task_sound_enabled', True)),
        'latest_unread_id': latest_unread.id if latest_unread else None,
    })


@tasks_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    TaskNotification.query.filter_by(user_id=current_user.id, is_read=False).update({TaskNotification.is_read: True, TaskNotification.read_at: datetime.utcnow()}, synchronize_session=False)
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})
    flash('Все уведомления отмечены как прочитанные', 'success')
    return redirect(url_for('tasks.notifications'))


@tasks_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def read_notification(notification_id):
    row = TaskNotification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    if not row.is_read:
        row.is_read = True
        row.read_at = datetime.utcnow()
        db.session.commit()
    return redirect(url_for('tasks.task_card', task_id=row.task_id))


@tasks_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def task_notification_settings():
    if request.method == 'POST':
        current_user.task_notifications_enabled = bool(request.form.get('task_notifications_enabled'))
        current_user.task_sound_enabled = bool(request.form.get('task_sound_enabled'))
        current_user.task_email_enabled = bool(request.form.get('task_email_enabled'))
        current_user.task_notify_only_important = bool(request.form.get('task_notify_only_important'))
        db.session.commit()
        flash('Настройки уведомлений сохранены', 'success')
        return redirect(url_for('tasks.task_notification_settings'))
    return render_template('tasks/settings.html', title='Настройки уведомлений по задачам', counts=_task_counts())


@tasks_bp.route('/email-log')
@login_required
def email_log():
    if getattr(current_user, 'role', None) not in ADMIN_ROLES:
        abort(403)
    rows = TaskEmailLog.query.order_by(TaskEmailLog.created_at.desc()).limit(300).all()
    return render_template('tasks/email_log.html', title='Журнал email-уведомлений', rows=rows, counts=_task_counts())


@tasks_bp.route('/print/<int:task_id>')
@login_required
def print_task(task_id):
    task = Task.query.get_or_404(task_id)
    if not _can_view_task(task):
        abort(403)
    comments = TaskComment.query.filter_by(task_id=task.id).order_by(TaskComment.created_at.asc()).all()
    history_entries = TaskHistory.query.filter_by(task_id=task.id).order_by(TaskHistory.created_at.asc()).all()
    return render_template('tasks/print_card.html', task=task, comments=comments, history_entries=history_entries, attachment_groups=_attachment_groups(task), format_file_size=_format_file_size)


@tasks_bp.route('/templates')
@login_required
def templates_list():
    rows = TaskTemplate.query.order_by(TaskTemplate.name.asc()).all()
    return render_template('tasks/templates_list.html', title='Шаблоны задач', templates=rows, counts=_task_counts())


@tasks_bp.route('/templates/new', methods=['GET', 'POST'])
@login_required
def template_new():
    if not _can_create_tasks():
        abort(403)
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        title_template = (request.form.get('title_template') or '').strip()
        if not name or not title_template:
            flash('Заполните название шаблона и заголовок задачи', 'danger')
        else:
            template = TaskTemplate(
                name=name,
                title_template=title_template,
                description_template=(request.form.get('description_template') or '').strip() or None,
                task_type_id=request.form.get('task_type_id', type=int) or None,
                priority=(request.form.get('priority') or 'обычный').strip(),
                default_deadline_days=request.form.get('default_deadline_days', type=int),
                is_control_required=bool(request.form.get('is_control_required')),
                created_by_user_id=current_user.id,
                is_active=bool(request.form.get('is_active', '1')),
            )
            db.session.add(template)
            db.session.flush()
            _save_template_checklist(template, request.form.get('checklist_text'))
            db.session.commit()
            flash('Шаблон сохранен', 'success')
            return redirect(url_for('tasks.templates_list'))
    return render_template('tasks/template_form.html', title='Новый шаблон задачи', task_types=TaskType.query.filter_by(is_active=True).order_by(TaskType.sort_order.asc(), TaskType.name.asc()).all(), priority_choices=Task.PRIORITY_CHOICES, counts=_task_counts())


@tasks_bp.route('/templates/<int:template_id>/apply')
@login_required
def apply_template(template_id):
    template = TaskTemplate.query.get_or_404(template_id)
    params = {
        'title': template.title_template,
        'description': template.description_template or '',
        'task_type_id': template.task_type_id or '',
        'priority': template.priority or 'обычный',
        'template_id': template.id,
        'checklist_text': '\n'.join(item.title for item in (template.checklist_items or [])),
    }
    if template.default_deadline_days:
        params['deadline_at'] = (datetime.utcnow() + timedelta(days=template.default_deadline_days)).strftime('%Y-%m-%dT%H:%M')
    if template.is_control_required:
        params['is_control_required'] = '1'
    return redirect(url_for('tasks.new_task', **params))


@tasks_bp.route('/batch/new', methods=['GET', 'POST'])
@login_required
def batch_new():
    if not _can_create_tasks():
        abort(403)
    template_id = request.form.get('template_id', type=int) if request.method == 'POST' else request.args.get('template_id', type=int)
    selected_template = TaskTemplate.query.get(template_id) if template_id else None
    current_year = _current_year()
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    selected_year_id = request.form.get('academic_year_id', type=int) if request.method == 'POST' else (current_year.id if current_year else None)
    selected_grade = request.form.get('grade', type=int) if request.method == 'POST' else None
    selected_class_id = request.form.get('class_id', type=int) if request.method == 'POST' else None
    grades = _grades_for_year(selected_year_id) if selected_year_id else []
    classes = _classes_for_grade(selected_year_id, selected_grade) if selected_year_id else []
    children = _children_for_class(selected_year_id, selected_class_id) if selected_year_id and selected_class_id else []
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        responsible_ids = [int(x) for x in request.form.getlist('responsible_user_ids') if str(x).isdigit()]
        child_ids = [int(x) for x in request.form.getlist('child_ids') if str(x).isdigit()]
        mode = (request.form.get('target_mode') or 'employees').strip()
        if not title:
            flash('Укажите название задачи', 'danger')
        elif mode == 'employees' and not responsible_ids:
            flash('Выберите хотя бы одного исполнителя', 'danger')
        elif mode == 'children' and not child_ids:
            flash('Выберите хотя бы одного обучающегося', 'danger')
        else:
            created = 0
            if mode == 'employees':
                for responsible_id in responsible_ids:
                    task = Task(
                        title=title,
                        description=(request.form.get('description') or '').strip() or None,
                        task_type_id=request.form.get('task_type_id', type=int) or None,
                        priority=(request.form.get('priority') or 'обычный').strip(),
                        status=Task.STATUS_NEW,
                        creator_user_id=current_user.id,
                        responsible_user_id=responsible_id,
                        controller_user_id=request.form.get('controller_user_id', type=int) or None,
                        academic_year_id=selected_year_id or None,
                        class_id=selected_class_id or None,
                        deadline_at=_parse_deadline(request.form.get('deadline_at')),
                        is_control_required=bool(request.form.get('is_control_required')),
                    )
                    db.session.add(task)
                    db.session.flush()
                    _save_checklist(task, request.form)
                    _add_history(task, 'Задача создана массово', event_type='batch_created')
                    _deliver_notifications(task, 'new_task', 'Новая задача', f'Вам назначена задача «{task.title}».')
                    created += 1
            else:
                responsible_id = request.form.get('responsible_user_id', type=int)
                if not responsible_id:
                    flash('Для постановки по детям укажите ответственного', 'danger')
                    return render_template('tasks/batch_form.html', title='Массовая постановка задач', years=years, grades=grades, classes=classes, children=children, selected_year_id=selected_year_id, selected_grade=selected_grade, selected_class_id=selected_class_id, users=User.query.filter(User.is_active_user.is_(True)).order_by(User.last_name.asc(), User.first_name.asc()).all(), task_types=TaskType.query.filter_by(is_active=True).order_by(TaskType.sort_order.asc(), TaskType.name.asc()).all(), priority_choices=Task.PRIORITY_CHOICES, counts=_task_counts())
                for child_id in child_ids:
                    task = Task(
                        title=title,
                        description=(request.form.get('description') or '').strip() or None,
                        task_type_id=request.form.get('task_type_id', type=int) or None,
                        priority=(request.form.get('priority') or 'обычный').strip(),
                        status=Task.STATUS_NEW,
                        creator_user_id=current_user.id,
                        responsible_user_id=responsible_id,
                        controller_user_id=request.form.get('controller_user_id', type=int) or None,
                        child_id=child_id,
                        class_id=selected_class_id or None,
                        academic_year_id=selected_year_id or None,
                        deadline_at=_parse_deadline(request.form.get('deadline_at')),
                        is_control_required=bool(request.form.get('is_control_required')),
                    )
                    db.session.add(task)
                    db.session.flush()
                    _save_checklist(task, request.form)
                    _add_history(task, 'Задача создана массово по списку обучающихся', event_type='batch_created')
                    _deliver_notifications(task, 'new_task', 'Новая задача', f'Вам назначена задача «{task.title}».')
                    created += 1
            db.session.commit()
            flash(f'Создано задач: {created}', 'success')
            return redirect(url_for('tasks.my_tasks'))
    return render_template('tasks/batch_form.html', title='Массовая постановка задач', years=years, grades=grades, classes=classes, children=children, selected_year_id=selected_year_id, selected_grade=selected_grade, selected_class_id=selected_class_id, users=User.query.filter(User.is_active_user.is_(True)).order_by(User.last_name.asc(), User.first_name.asc()).all(), task_types=TaskType.query.filter_by(is_active=True).order_by(TaskType.sort_order.asc(), TaskType.name.asc()).all(), priority_choices=Task.PRIORITY_CHOICES, counts=_task_counts())


@tasks_bp.route('/auto/demo/document-overdue', methods=['POST'])
@login_required
def auto_demo_document_overdue():
    if getattr(current_user, 'role', None) not in ADMIN_ROLES:
        abort(403)
    responsible_user_id = request.form.get('responsible_user_id', type=int) or current_user.id
    task = Task(
        title='Проверить просроченный документ обучающегося',
        description='Автоматически созданная демонстрационная задача по сценарию просрочки документа.',
        priority='высокий',
        status=Task.STATUS_NEW,
        creator_user_id=current_user.id,
        responsible_user_id=responsible_user_id,
        deadline_at=datetime.utcnow() + timedelta(days=2),
        is_control_required=True,
    )
    db.session.add(task)
    db.session.flush()
    _add_history(task, 'Задача создана автоматически по правилу document_overdue', event_type='auto_created')
    _deliver_notifications(task, 'auto_created', 'Автозадача', f'Создана автоматическая задача «{task.title}».')
    db.session.commit()
    flash('Демонстрационная автозадача создана', 'success')
    return redirect(url_for('tasks.task_card', task_id=task.id))


@tasks_bp.route('/analytics')
@login_required
def analytics():
    scope = request.args.get('scope', 'my').strip()
    if scope == 'all' and getattr(current_user, 'role', None) not in ADMIN_ROLES:
        scope = 'my'
    query = _apply_filters(_task_scope_query(scope))
    analytics_data = _task_analytics_context(query)
    return render_template('tasks/analytics.html', title='Аналитика по задачам', scope=scope, counts=_task_counts(), analytics=analytics_data, **_common_filter_context())


@tasks_bp.route('/export.xlsx')
@login_required
def export_tasks_xlsx():
    scope = request.args.get('scope', 'my').strip()
    if scope == 'all' and getattr(current_user, 'role', None) not in ADMIN_ROLES:
        scope = 'my'
    query = _apply_filters(_task_scope_query(scope))
    tasks = _ordered_task_rows(query)
    stream = _build_tasks_workbook(tasks, title='Задачи')
    filename = f'tasks_{scope}_{datetime.utcnow().strftime("%Y%m%d_%H%M")}.xlsx'
    return send_file(stream, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@tasks_bp.route('/<int:task_id>')
@login_required
def task_card(task_id):
    task = Task.query.get_or_404(task_id)
    if not _can_view_task(task):
        abort(403)
    comments = TaskComment.query.filter_by(task_id=task.id).order_by(TaskComment.created_at.desc()).all()
    history_entries = TaskHistory.query.filter_by(task_id=task.id).order_by(TaskHistory.created_at.desc()).all()

    # Связанный инцидент (если задача создана из инцидента)
    linked_incident = None
    try:
        linked_incident_id = getattr(task, 'incident_id', None)
        if linked_incident_id:
            from app.models_legacy import Incident as _Incident
            linked_incident = _Incident.query.get(linked_incident_id)
    except Exception:
        linked_incident = None

    return render_template('tasks/card.html', task=task, comments=comments, history_entries=history_entries, status_choices=Task.STATUS_CHOICES, can_edit=_can_edit_task(task), can_delete_task=_can_delete_task(task), counts=_task_counts(), attachment_groups=_attachment_groups(task), format_file_size=_format_file_size, can_delete_attachment=_can_delete_attachment, linked_incident=linked_incident)


@tasks_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    if not _can_edit_task(task):
        abort(403)

    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    selected_year_id = request.form.get('academic_year_id', type=int) if request.method == 'POST' else task.academic_year_id
    selected_grade = request.form.get('grade', type=int) if request.method == 'POST' else getattr(task.school_class, 'grade', None)
    selected_class_id = request.form.get('class_id', type=int) if request.method == 'POST' else task.class_id

    grades = _grades_for_year(selected_year_id) if selected_year_id else []
    classes = _classes_for_grade(selected_year_id, selected_grade) if selected_year_id else []
    children = _children_for_class(selected_year_id, selected_class_id) if selected_year_id and selected_class_id else []

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip() or None
        responsible_user_id = request.form.get('responsible_user_id', type=int)
        controller_user_id = request.form.get('controller_user_id', type=int)
        child_id = request.form.get('child_id', type=int)
        if not title:
            flash('Укажите название задачи', 'danger')
        elif not responsible_user_id:
            flash('Укажите ответственного', 'danger')
        else:
            old_data = {
                'status': task.status,
                'deadline_at': task.deadline_at,
                'responsible_user_id': task.responsible_user_id,
                'priority': task.priority,
                'description': task.description,
                'child_id': task.child_id,
                'completed_at': task.completed_at,
            }
            task.title = title
            task.description = description
            task.task_type_id = request.form.get('task_type_id', type=int) or None
            priority = (request.form.get('priority') or 'обычный').strip()
            task.priority = priority if priority in Task.PRIORITY_CHOICES else 'обычный'
            task.responsible_user_id = responsible_user_id
            task.controller_user_id = controller_user_id or None
            task.academic_year_id = selected_year_id or None
            task.class_id = selected_class_id or None
            task.child_id = child_id or None
            task.deadline_at = _parse_deadline(request.form.get('deadline_at'))
            task.is_control_required = bool(request.form.get('is_control_required'))
            task.is_private = bool(request.form.get('is_private'))
            task.result_text = (request.form.get('result_text') or '').strip() or None
            coexecutor_ids = [int(x) for x in request.form.getlist('coexecutor_user_ids') if str(x).isdigit()]
            observer_ids = [int(x) for x in request.form.getlist('observer_user_ids') if str(x).isdigit()]
            _replace_participants(task, coexecutor_ids=coexecutor_ids, observer_ids=observer_ids, controller_id=controller_user_id)
            _save_checklist(task, request.form)
            try:
                _handle_task_attachments_from_form(task)
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), 'danger')
                return render_template('tasks/form.html',
                                       title='Редактирование задачи',
                                       task=task,
                                       parent_task=task.parent_task,
                                       template_defaults={},
                                       selected_template=None,
                                       grades=grades,
                                       classes=classes,
                                       children=children,
                                       selected_year_id=selected_year_id,
                                       selected_grade=selected_grade,
                                       selected_class_id=selected_class_id,
                                       selected_child_id=(task.child_id if task else None),
                                       **_common_filter_context())
            _track_task_field_changes(task, old_data)
            _add_history(task, 'Карточка задачи обновлена', event_type='updated')
            if old_data.get('deadline_at') != task.deadline_at:
                _deliver_notifications(task, 'deadline_changed', 'Изменен срок задачи', f'По задаче «{task.title}» изменен срок исполнения.')
            else:
                _deliver_notifications(task, 'task_updated', 'Задача обновлена', f'По задаче «{task.title}» обновлены данные.')
            db.session.commit()
            flash('Задача обновлена', 'success')
            return redirect(url_for('tasks.task_card', task_id=task.id))

    return render_template('tasks/form.html',
                           title='Редактирование задачи',
                           task=task,
                           parent_task=task.parent_task,
                           template_defaults={},
                           selected_template=None,
                           grades=grades,
                           classes=classes,
                           children=children,
                           selected_year_id=selected_year_id,
                           selected_grade=selected_grade,
                           selected_class_id=selected_class_id,
                           selected_child_id=(task.child_id if task else None),
                           **_common_filter_context())


@tasks_bp.route('/<int:task_id>/status', methods=['POST'])
@login_required
def change_status(task_id):
    # s81: with_for_update — row-lock на PG, защита от race при одновременной
    # смене статуса (двойной клик / два устройства). На SQLite no-op.
    task = Task.query.filter_by(id=task_id).with_for_update().first()
    if task is None:
        abort(404)
    if not _can_edit_task(task):
        abort(403)
    status = (request.form.get('status') or '').strip()
    if status not in Task.STATUS_CHOICES:
        flash('Недопустимый статус', 'danger')
        return redirect(url_for('tasks.task_card', task_id=task.id))
    if not task.can_transition_to(status):
        flash('Недопустимый переход между статусами', 'danger')
        return redirect(url_for('tasks.task_card', task_id=task.id))
    old_status = task.status
    task.status = status
    if status in {Task.STATUS_DONE, Task.STATUS_CLOSED}:
        task.completed_at = datetime.utcnow()
    elif old_status in {Task.STATUS_DONE, Task.STATUS_CLOSED} and status == Task.STATUS_REWORK:
        task.completed_at = None
    db.session.add(TaskComment(task_id=task.id, author_user_id=current_user.id, comment_text=f'Изменен статус: {status}', is_system_comment=True))
    _add_history(task, f'Изменен статус: {old_status} → {status}', event_type='status_changed', field_name='status', old_value=old_status, new_value=status)
    if status == Task.STATUS_REVIEW:
        _add_history(task, 'Задача отправлена на проверку', event_type='sent_to_review')
    elif status == Task.STATUS_REWORK:
        _add_history(task, 'Задача возвращена на доработку', event_type='returned_for_rework')
    elif status in {Task.STATUS_DONE, Task.STATUS_CLOSED}:
        _add_history(task, 'Задача закрыта', event_type='closed')

    # Task → Incident sync: при закрытии задачи, созданной из инцидента,
    # автоматически переводим инцидент в "resolved" (если он ещё не закрыт).
    if status in {Task.STATUS_DONE, Task.STATUS_CLOSED} and getattr(task, 'incident_id', None):
        try:
            from app.models_legacy import Incident, IncidentStatusHistory
            inc = Incident.query.get(task.incident_id)
            if inc and inc.status not in ('resolved', 'closed'):
                prev_status = inc.status
                inc.status = 'resolved'
                db.session.add(IncidentStatusHistory(
                    incident_id=inc.id,
                    from_status=prev_status,
                    to_status='resolved',
                    changed_by_id=getattr(current_user, 'id', None),
                    comment=f'Автоматически: закрыта связанная задача #{task.id}',
                ))
        except Exception:
            pass

    notification_type = 'status_changed'
    notification_title = 'Изменение статуса задачи'
    notification_message = f'По задаче «{task.title}» установлен статус «{status}».'
    if status == Task.STATUS_REVIEW:
        notification_type = 'sent_to_review'
        notification_title = 'Задача отправлена на проверку'
        notification_message = f'Задача «{task.title}» отправлена на проверку.'
    elif status == Task.STATUS_REWORK:
        notification_type = 'returned_for_rework'
        notification_title = 'Задача возвращена на доработку'
        notification_message = f'Задача «{task.title}» возвращена на доработку.'
    elif status in {Task.STATUS_DONE, Task.STATUS_CLOSED}:
        notification_type = 'closed'
        notification_title = 'Задача закрыта'
        notification_message = f'Задача «{task.title}» закрыта.'
    _deliver_notifications(task, notification_type, notification_title, notification_message)
    db.session.commit()
    flash('Статус обновлен', 'success')
    return redirect(url_for('tasks.task_card', task_id=task.id))


@tasks_bp.route('/<int:task_id>/comment', methods=['POST'])
@login_required
def add_comment(task_id):
    task = Task.query.get_or_404(task_id)
    if not _can_view_task(task):
        abort(403)
    text = (request.form.get('comment_text') or '').strip()
    if not text:
        flash('Введите комментарий', 'danger')
        return redirect(url_for('tasks.task_card', task_id=task.id))
    db.session.add(TaskComment(task_id=task.id, author_user_id=current_user.id, comment_text=text))
    _add_history(task, 'Добавлен комментарий', event_type='comment_added')
    _deliver_notifications(task, 'comment_added', 'Новый комментарий', f'По задаче «{task.title}» добавлен комментарий.')
    db.session.commit()
    flash('Комментарий добавлен', 'success')
    return redirect(url_for('tasks.task_card', task_id=task.id))




@tasks_bp.route('/<int:task_id>/attachments/upload', methods=['POST'])
@login_required
def upload_attachment(task_id):
    task = Task.query.get_or_404(task_id)
    if not _can_edit_task(task):
        abort(403)
    file_kind = (request.form.get('file_kind') or TaskAttachment.FILE_KIND_WORK).strip()
    files = request.files.getlist('files')
    try:
        saved = _save_uploaded_attachments(task, files, file_kind)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('tasks.task_card', task_id=task.id))
    db.session.commit()
    flash('Файл загружен' if len(saved) == 1 else f'Загружено файлов: {len(saved)}', 'success')
    return redirect(url_for('tasks.task_card', task_id=task.id))




@tasks_bp.route('/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    if not _can_delete_task(task):
        abort(403)

    next_url = request.form.get('next') or request.args.get('next') or url_for('tasks.created_by_me')

    try:
        _delete_task_related_data(task)
        db.session.flush()
        db.session.delete(task)
        db.session.commit()
        flash('Задача удалена', 'success')
        return redirect(next_url)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Ошибка удаления задачи id=%s: %s', task.id, e)
        flash(f'Не удалось удалить задачу: {e}', 'danger')
        return redirect(url_for('tasks.task_card', task_id=task.id))

@tasks_bp.route('/<int:task_id>/attachments/<int:attachment_id>/download')
@login_required
def download_attachment(task_id, attachment_id):
    task = Task.query.get_or_404(task_id)
    if not _can_view_task(task):
        abort(403)
    attachment = TaskAttachment.query.filter_by(task_id=task.id, id=attachment_id, is_deleted=False).first_or_404()
    path = _task_abs_path(attachment.file_path)
    if not path or not os.path.isfile(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=attachment.filename)


@tasks_bp.route('/<int:task_id>/attachments/<int:attachment_id>/delete', methods=['POST'])
@login_required
def delete_attachment(task_id, attachment_id):
    task = Task.query.get_or_404(task_id)
    attachment = TaskAttachment.query.filter_by(task_id=task.id, id=attachment_id, is_deleted=False).first_or_404()
    if not _can_delete_attachment(task, attachment):
        abort(403)
    attachment.is_deleted = True
    attachment.deleted_at = datetime.utcnow()
    attachment.deleted_by_user_id = current_user.id
    path = _task_abs_path(attachment.file_path)
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except Exception:
            pass
    _add_history(task, f'Удален файл: {attachment.filename}', event_type='attachment_deleted', old_value=attachment.filename)
    db.session.commit()
    flash('Вложение удалено', 'success')
    return redirect(url_for('tasks.task_card', task_id=task.id))

@tasks_bp.route('/<int:task_id>/checklist/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_checklist(task_id, item_id):
    task = Task.query.get_or_404(task_id)
    if not _can_edit_task(task):
        abort(403)
    item = TaskChecklistItem.query.filter_by(task_id=task.id, id=item_id).first_or_404()
    item.is_done = not item.is_done
    if item.is_done:
        item.completed_at = datetime.utcnow()
        item.completed_by_user_id = current_user.id
        _add_history(task, f'Выполнен пункт чек-листа: {item.title}', event_type='checklist_done')
    else:
        item.completed_at = None
        item.completed_by_user_id = None
        _add_history(task, f'Пункт чек-листа снова открыт: {item.title}', event_type='checklist_reopen')
    db.session.commit()
    flash('Чек-лист обновлен', 'success')
    return redirect(url_for('tasks.task_card', task_id=task.id))
