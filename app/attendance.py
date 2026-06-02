from __future__ import annotations

from datetime import date, datetime, time
import os
from typing import Optional
from types import SimpleNamespace

from flask import Blueprint, flash, redirect, render_template, request, url_for, current_app
from flask_login import current_user, login_required
from sqlalchemy import func, text
from werkzeug.utils import secure_filename

from app.core.extensions import db
from app.core.cache import cache
from app.permissions import has_any_role
from app.models import AcademicYear, Building, Child, ChildEnrollment, SchoolClass, User
from app.services.attendance_import_service import import_attendance_report, delete_import_session
from app.services.attendance_stats_service import (
    build_attendance_dashboard_stats,
    build_month_analytics,
    get_default_month,
    get_month_choices,
)

attendance_bp = Blueprint("attendance", __name__, url_prefix="/attendance")


class AttendanceLate(db.Model):
    __tablename__ = "attendance_late"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    late_date = db.Column(db.Date, nullable=False, index=True)
    late_time = db.Column(db.Time, nullable=True)
    norm_time = db.Column(db.Time, nullable=True)
    late_minutes = db.Column(db.Integer, nullable=True)
    source = db.Column(db.String(30), nullable=False, default="IMPORT")
    import_session_id = db.Column(db.Integer, db.ForeignKey("attendance_import_session.id"), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    child = db.relationship("Child")
    school_class = db.relationship("SchoolClass")
    creator = db.relationship("User", foreign_keys=[created_by])


class AttendancePass(db.Model):
    __tablename__ = "attendance_pass"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    pass_date = db.Column(db.Date, nullable=False, index=True)
    pass_time = db.Column(db.Time, nullable=True)
    reason = db.Column(db.String(500), nullable=True)
    issued_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="created", index=True)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    child = db.relationship("Child")
    school_class = db.relationship("SchoolClass")
    issuer = db.relationship("User", foreign_keys=[issued_by])


class AttendanceImportSession(db.Model):
    __tablename__ = "attendance_import_session"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    imported_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    period_month = db.Column(db.String(7), nullable=True, index=True)
    period_year = db.Column(db.Integer, nullable=True, index=True)
    period_num = db.Column(db.Integer, nullable=True, index=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True, index=True)

    rows_total = db.Column(db.Integer, nullable=False, default=0)
    rows_processed = db.Column(db.Integer, nullable=False, default=0)
    rows_matched = db.Column(db.Integer, nullable=False, default=0)
    rows_unmatched = db.Column(db.Integer, nullable=False, default=0)
    rows_late = db.Column(db.Integer, nullable=False, default=0)
    rows_early_leave = db.Column(db.Integer, nullable=False, default=0)
    rows_absent = db.Column(db.Integer, nullable=False, default=0)
    rows_no_entry = db.Column(db.Integer, nullable=False, default=0)
    rows_no_exit = db.Column(db.Integer, nullable=False, default=0)
    unique_classes = db.Column(db.Integer, nullable=False, default=0)
    unique_children = db.Column(db.Integer, nullable=False, default=0)
    school_days_count = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    importer = db.relationship("User", foreign_keys=[imported_by])
    building = db.relationship("Building", foreign_keys=[building_id])


class AttendanceRawEntry(db.Model):
    __tablename__ = "attendance_raw_entry"

    id = db.Column(db.Integer, primary_key=True)
    import_session_id = db.Column(db.Integer, db.ForeignKey("attendance_import_session.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=True, index=True)
    full_name = db.Column(db.String(255), nullable=True, index=True)
    source_class_name = db.Column(db.String(120), nullable=True, index=True)
    entry_date = db.Column(db.Date, nullable=True, index=True)
    first_in = db.Column(db.Time, nullable=True)
    last_out = db.Column(db.Time, nullable=True)
    presence_minutes = db.Column(db.Integer, nullable=True)
    presence_text = db.Column(db.String(120), nullable=True)
    inputs_outputs = db.Column(db.String(255), nullable=True)
    is_late = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_absent = db.Column(db.Boolean, nullable=False, default=False)
    is_early_leave = db.Column(db.Boolean, nullable=False, default=False)
    no_entry_fix = db.Column(db.Boolean, nullable=False, default=False)
    no_exit_fix = db.Column(db.Boolean, nullable=False, default=False)
    matched_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    raw_payload = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    import_session = db.relationship(
        "AttendanceImportSession",
        backref=db.backref("entries", lazy=True, cascade="all, delete-orphan")
    )
    child = db.relationship("Child")
    school_class = db.relationship("SchoolClass")


_attendance_schema_checked = False


def _ensure_attendance_schema() -> None:
    global _attendance_schema_checked
    if _attendance_schema_checked:
        return
    statements = [
        "ALTER TABLE attendance_schedule_rule ADD COLUMN IF NOT EXISTS grade INTEGER",
        "ALTER TABLE attendance_schedule_rule ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE",
        "UPDATE attendance_schedule_rule SET grade = grade_from WHERE grade IS NULL AND grade_from IS NOT NULL AND grade_from = grade_to",
        "UPDATE attendance_schedule_rule SET updated_at = created_at WHERE updated_at IS NULL",
        "CREATE TABLE IF NOT EXISTS attendance_schedule_rule_class (id SERIAL PRIMARY KEY, rule_id INTEGER NOT NULL REFERENCES attendance_schedule_rule(id) ON DELETE CASCADE, class_id INTEGER NOT NULL REFERENCES school_class(id) ON DELETE CASCADE, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW())",
        "CREATE INDEX IF NOT EXISTS ix_attendance_schedule_rule_class_rule_id ON attendance_schedule_rule_class(rule_id)",
        "CREATE INDEX IF NOT EXISTS ix_attendance_schedule_rule_class_class_id ON attendance_schedule_rule_class(class_id)",
        "CREATE TABLE IF NOT EXISTS attendance_school_day (id SERIAL PRIMARY KEY, day_date DATE NOT NULL UNIQUE, month_key VARCHAR(7) NOT NULL, is_school_day BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(), updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW())",
        "CREATE INDEX IF NOT EXISTS ix_attendance_school_day_month_key ON attendance_school_day(month_key)",
        "CREATE INDEX IF NOT EXISTS ix_attendance_school_day_day_date ON attendance_school_day(day_date)",
        "ALTER TABLE attendance_import_session ADD COLUMN IF NOT EXISTS school_days_count INTEGER",
        "ALTER TABLE attendance_import_session ADD COLUMN IF NOT EXISTS period_year INTEGER",
        "ALTER TABLE attendance_import_session ADD COLUMN IF NOT EXISTS period_num INTEGER",
        "ALTER TABLE attendance_import_session ADD COLUMN IF NOT EXISTS building_id INTEGER",
        "CREATE INDEX IF NOT EXISTS ix_attendance_import_session_period_year ON attendance_import_session(period_year)",
        "CREATE INDEX IF NOT EXISTS ix_attendance_import_session_period_num ON attendance_import_session(period_num)",
        "CREATE INDEX IF NOT EXISTS ix_attendance_import_session_building_id ON attendance_import_session(building_id)",
        "CREATE INDEX IF NOT EXISTS ix_attendance_import_session_year_month ON attendance_import_session(period_year, period_num)",
        "CREATE INDEX IF NOT EXISTS ix_attendance_import_session_imported_at ON attendance_import_session(imported_at)",
        "CREATE INDEX IF NOT EXISTS ix_attendance_raw_entry_child_entry_date ON attendance_raw_entry(child_id, entry_date)",
        "CREATE INDEX IF NOT EXISTS ix_attendance_raw_entry_entry_date_class ON attendance_raw_entry(entry_date, matched_class_id)",
        "CREATE INDEX IF NOT EXISTS ix_attendance_late_date_class ON attendance_late(late_date, class_id)",
        "CREATE INDEX IF NOT EXISTS ix_child_name_parts ON child(last_name, first_name, middle_name)",
        "CREATE INDEX IF NOT EXISTS ix_school_class_grade_building ON school_class(grade, building_id)",
    ]
    for sql in statements:
        db.session.execute(text(sql))
    db.session.commit()
    _attendance_schema_checked = True


class AttendanceSchoolDay(db.Model):
    __tablename__ = "attendance_school_day"

    id = db.Column(db.Integer, primary_key=True)
    day_date = db.Column(db.Date, nullable=False, unique=True, index=True)
    month_key = db.Column(db.String(7), nullable=False, index=True)
    is_school_day = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)


class AttendanceScheduleRule(db.Model):
    __tablename__ = "attendance_schedule_rule"

    id = db.Column(db.Integer, primary_key=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    school_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    grade_from = db.Column(db.Integer, nullable=True)
    grade_to = db.Column(db.Integer, nullable=True)
    grade = db.Column(db.Integer, nullable=True, index=True)
    start_time = db.Column(db.Time, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    comment = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    academic_year = db.relationship("AcademicYear")
    school_class = db.relationship("SchoolClass")
    class_links = db.relationship("AttendanceScheduleRuleClass", backref="rule", lazy=True, cascade="all, delete-orphan")


class AttendanceScheduleRuleClass(db.Model):
    __tablename__ = "attendance_schedule_rule_class"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("attendance_schedule_rule.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    school_class = db.relationship("SchoolClass")


def _iter_month_dates(month: str):
    year, mon = map(int, month.split('-'))
    from calendar import monthrange
    days_in_month = monthrange(year, mon)[1]
    for day in range(1, days_in_month + 1):
        yield date(year, mon, day)


def _get_school_days_for_month(month: str):
    rows = AttendanceSchoolDay.query.filter_by(month_key=month).order_by(AttendanceSchoolDay.day_date.asc()).all()
    if rows:
        return rows
    generated = []
    for day in _iter_month_dates(month):
        generated.append(SimpleNamespace(day_date=day, month_key=month, is_school_day=day.weekday() < 5))
    return generated


def _default_school_days_for_month(month: str):
    return [day for day in _iter_month_dates(month) if day.weekday() < 5]


def _save_school_days_for_month(month: str, selected_dates: list[date]):
    AttendanceSchoolDay.query.filter_by(month_key=month).delete()
    selected_set = set(selected_dates)
    for day in _iter_month_dates(month):
        db.session.add(AttendanceSchoolDay(day_date=day, month_key=month, is_school_day=day in selected_set))
    db.session.commit()
    cache.clear()


def _parse_selected_school_days(month: str, values: list[str]):
    selected = []
    valid = {d.isoformat(): d for d in _iter_month_dates(month)}
    for value in values:
        if value in valid:
            selected.append(valid[value])
    return sorted(set(selected))


def _current_year():
    return AcademicYear.query.filter_by(is_current=True).first()


def _ensure_schedule_rules() -> None:
    _ensure_attendance_schema()
    if AttendanceScheduleRule.query.count() > 0:
        return
    current_year = _current_year()
    db.session.add(
        AttendanceScheduleRule(
            title="1-4 классы",
            grade=1,
            grade_from=1,
            grade_to=1,
            start_time=time(8, 30),
            academic_year_id=getattr(current_year, 'id', None),
        )
    )
    db.session.add(
        AttendanceScheduleRule(
            title="5-9 классы",
            grade=5,
            grade_from=5,
            grade_to=5,
            start_time=time(8, 0),
            academic_year_id=getattr(current_year, 'id', None),
        )
    )
    db.session.add(
        AttendanceScheduleRule(
            title="10-11 классы",
            grade=10,
            grade_from=10,
            grade_to=10,
            start_time=time(8, 30),
            academic_year_id=getattr(current_year, 'id', None),
        )
    )
    db.session.commit()


def _can_issue_pass() -> bool:
    return has_any_role("ADMIN", "CLASS_TEACHER", "SOCIAL_PEDAGOG")


def _can_import() -> bool:
    return getattr(current_user, "role", None) == "ADMIN"


def _accessible_classes():
    current_year = _current_year()
    query = SchoolClass.query.filter(SchoolClass.is_archived.is_(False))
    if current_year:
        query = query.filter(SchoolClass.academic_year_id == current_year.id)
    if getattr(current_user, "role", None) == "CLASS_TEACHER":
        query = query.filter(SchoolClass.teacher_user_id == current_user.id)
    return query.order_by(SchoolClass.grade.asc().nulls_last(), SchoolClass.name.asc()).all()


def _children_for_class(class_id: Optional[int] = None):
    current_year = _current_year()
    query = Child.query.join(ChildEnrollment, ChildEnrollment.child_id == Child.id).filter(ChildEnrollment.ended_at.is_(None))
    if current_year:
        query = query.filter(ChildEnrollment.academic_year_id == current_year.id)
    if class_id:
        query = query.filter(ChildEnrollment.school_class_id == class_id)
    elif getattr(current_user, "role", None) == "CLASS_TEACHER":
        class_ids = [c.id for c in _accessible_classes()]
        if class_ids:
            query = query.filter(ChildEnrollment.school_class_id.in_(class_ids))
        else:
            query = query.filter(db.text("1=0"))
    return query.order_by(Child.last_name.asc(), Child.first_name.asc(), Child.middle_name.asc()).all()


def _filter_passes_query():
    query = AttendancePass.query.join(Child, AttendancePass.child_id == Child.id).outerjoin(SchoolClass, AttendancePass.class_id == SchoolClass.id)
    if getattr(current_user, "role", None) == "CLASS_TEACHER":
        class_ids = [c.id for c in _accessible_classes()]
        if class_ids:
            query = query.filter(AttendancePass.class_id.in_(class_ids))
        else:
            query = query.filter(db.text("1=0"))
    return query


def _get_classes_by_grade(classes):
    result = {}
    for item in classes:
        if item.grade is not None:
            result.setdefault(int(item.grade), []).append(item)
    return result


def _rule_classes(rule: AttendanceScheduleRule):
    linked = [x.school_class for x in rule.class_links if x.school_class]
    if linked:
        return linked
    if rule.school_class:
        return [rule.school_class]
    if rule.grade is not None:
        current_year = _current_year()
        query = SchoolClass.query.filter(SchoolClass.is_archived.is_(False), SchoolClass.grade == rule.grade)
        if current_year:
            query = query.filter(SchoolClass.academic_year_id == current_year.id)
        return query.order_by(SchoolClass.name.asc()).all()
    if rule.grade_from and rule.grade_to:
        current_year = _current_year()
        query = SchoolClass.query.filter(
            SchoolClass.is_archived.is_(False),
            SchoolClass.grade >= rule.grade_from,
            SchoolClass.grade <= rule.grade_to,
        )
        if current_year:
            query = query.filter(SchoolClass.academic_year_id == current_year.id)
        return query.order_by(SchoolClass.grade.asc(), SchoolClass.name.asc()).all()
    return []


def _serialize_rule(rule: AttendanceScheduleRule):
    classes = _rule_classes(rule)
    return {
        'id': rule.id,
        'title': rule.title,
        'comment': rule.comment,
        'start_time': rule.start_time,
        'is_active': rule.is_active,
        'grade': rule.grade,
        'class_count': len(classes),
        'classes': classes,
        'mode_label': 'Класс' if rule.school_class_id or rule.class_links else ('Параллель' if rule.grade is not None else 'Диапазон'),
    }


def _find_conflicts(selected_class_ids, editing_rule_id=None):
    conflicts = []
    if not selected_class_ids:
        return conflicts
    rows = AttendanceScheduleRule.query.filter(AttendanceScheduleRule.is_active.is_(True))
    if editing_rule_id:
        rows = rows.filter(AttendanceScheduleRule.id != editing_rule_id)
    for rule in rows.all():
        rule_class_ids = {c.id for c in _rule_classes(rule)}
        overlap = sorted(rule_class_ids.intersection(set(selected_class_ids)))
        if overlap:
            classes = SchoolClass.query.filter(SchoolClass.id.in_(overlap)).order_by(SchoolClass.name.asc()).all()
            conflicts.append({'rule': rule, 'classes': classes})
    return conflicts


def resolve_start_time_for_class(school_class):
    if not school_class:
        return time(9, 0)
    direct = AttendanceScheduleRule.query.filter_by(is_active=True, school_class_id=school_class.id).order_by(AttendanceScheduleRule.updated_at.desc()).first()
    if direct:
        return direct.start_time
    link = (
        AttendanceScheduleRule.query.join(AttendanceScheduleRuleClass, AttendanceScheduleRuleClass.rule_id == AttendanceScheduleRule.id)
        .filter(AttendanceScheduleRule.is_active.is_(True), AttendanceScheduleRuleClass.class_id == school_class.id)
        .order_by(AttendanceScheduleRule.updated_at.desc())
        .first()
    )
    if link:
        return link.start_time
    grade_rule = AttendanceScheduleRule.query.filter(
        AttendanceScheduleRule.is_active.is_(True),
        AttendanceScheduleRule.grade == getattr(school_class, 'grade', None),
    ).order_by(AttendanceScheduleRule.updated_at.desc()).first()
    if grade_rule:
        return grade_rule.start_time
    legacy = AttendanceScheduleRule.query.filter(
        AttendanceScheduleRule.is_active.is_(True),
        AttendanceScheduleRule.school_class_id.is_(None),
        AttendanceScheduleRule.grade_from <= getattr(school_class, 'grade', 0),
        AttendanceScheduleRule.grade_to >= getattr(school_class, 'grade', 0),
    ).order_by(AttendanceScheduleRule.updated_at.desc()).first()
    if legacy:
        return legacy.start_time
    return time(9, 0)


@attendance_bp.before_app_request
def _attendance_bootstrap_once():
    try:
        _ensure_attendance_schema()
        _ensure_schedule_rules()
    except Exception:
        db.session.rollback()


@attendance_bp.route("/passes")
@login_required
def passes_registry():
    if not has_any_role("ADMIN", "CLASS_TEACHER", "KPP", "SOCIAL_PEDAGOG"):
        return redirect(url_for("main.dashboard"))
    status = (request.args.get("status") or "").strip().lower()
    q = _filter_passes_query()
    if status:
        q = q.filter(func.lower(AttendancePass.status) == status)
    rows = q.order_by(AttendancePass.pass_date.desc(), AttendancePass.created_at.desc()).all()
    stats = build_attendance_dashboard_stats(current_user)
    return render_template("attendance_passes.html", rows=rows, stats=stats, status=status)


@attendance_bp.route("/passes/new", methods=["GET", "POST"])
@login_required
def new_pass():
    if not _can_issue_pass():
        return redirect(url_for("main.dashboard"))
    classes = _accessible_classes()
    class_id = request.values.get("class_id", type=int)
    selected_grade = request.values.get("grade", type=int)
    classes_by_grade = _get_classes_by_grade(classes)
    if selected_grade is None and class_id:
        selected_class = next((item for item in classes if item.id == class_id), None)
        if selected_class and selected_class.grade is not None:
            selected_grade = int(selected_class.grade)
    filtered_classes = classes_by_grade.get(selected_grade, []) if selected_grade is not None else classes
    if request.method == "POST":
        child_id = request.form.get("child_id", type=int)
        class_id = request.form.get("class_id", type=int)
        selected_grade = request.form.get("grade", type=int) or selected_grade
        reason = (request.form.get("reason") or "").strip()
        pass_date = request.form.get("pass_date") or date.today().isoformat()
        pass_time_raw = request.form.get("pass_time") or datetime.now().strftime("%H:%M")
        child = Child.query.get_or_404(child_id)
        allowed_child_ids = {c.id for c in _children_for_class(class_id)}
        if child.id not in allowed_child_ids:
            flash("Нельзя оформить пропуск для этого ученика.", "danger")
            return redirect(url_for("attendance.new_pass", grade=selected_grade or "", class_id=class_id or ""))
        try:
            pass_time_value = datetime.strptime(pass_time_raw, "%H:%M").time()
        except Exception:
            pass_time_value = datetime.now().time().replace(second=0, microsecond=0)
        row = AttendancePass(
            child_id=child.id,
            class_id=class_id or getattr(child.current_class, "id", None),
            pass_date=datetime.strptime(pass_date, "%Y-%m-%d").date(),
            pass_time=pass_time_value,
            reason=reason or None,
            issued_by=current_user.id,
            status="created",
        )
        db.session.add(row)
        db.session.commit()
        flash("Пропуск оформлен.", "success")
        return redirect(url_for("attendance.passes_registry"))
    children = _children_for_class(class_id) if class_id else []
    return render_template(
        "attendance_pass_new.html",
        classes=classes,
        filtered_classes=filtered_classes,
        available_grades=sorted(classes_by_grade.keys()),
        children=children,
        selected_class_id=class_id,
        selected_grade=selected_grade,
        today=date.today(),
        now=datetime.now(),
    )


@attendance_bp.route("/import", methods=["GET", "POST"])
@login_required
def import_view():
    if not _can_import():
        return redirect(url_for("main.dashboard"))
    default_month = get_default_month()
    default_year, default_mon = default_month.split("-")
    selected_year = (request.values.get("period_year") or default_year).strip()
    selected_mon = (request.values.get("period_month_num") or default_mon).strip()
    selected_month = f"{selected_year}-{selected_mon}"
    if request.method == "POST":
        f = request.files.get("file")
        period_year = (request.form.get("period_year") or default_year).strip()
        period_month_num = (request.form.get("period_month_num") or default_mon).strip()
        building_id = request.form.get("building_id", type=int)
        period_month = f"{period_year}-{period_month_num}"
        selected_days_raw = request.form.getlist('school_days')
        selected_days = _parse_selected_school_days(period_month, selected_days_raw)
        if not selected_days:
            selected_days = _default_school_days_for_month(period_month)
            flash(
                "Учебные дни не были переданы формой для выбранного месяца. Автоматически выбраны будние дни месяца.",
                "warning",
            )
        _save_school_days_for_month(period_month, selected_days)
        if not f or not f.filename:
            flash("Выберите файл отчёта Excel.", "danger")
            return redirect(url_for("attendance.import_view", period_year=period_year, period_month_num=period_month_num))
        filename = secure_filename(f.filename)
        uploads_dir = current_app.config.get("UPLOAD_FOLDER")
        os.makedirs(uploads_dir, exist_ok=True)
        target_path = os.path.join(uploads_dir, filename)
        f.save(target_path)
        result = import_attendance_report(
            target_path,
            filename=filename,
            imported_by=current_user.id,
            period_month=period_month,
            school_days=selected_days,
            building_id=building_id,
        )
        if result.get("ok"):
            cache.clear()
            flash(result.get("message") or "Импорт завершён.", "success")
            return redirect(url_for("attendance.analytics", month=result.get("period_month") or period_month))
        flash(result.get("message") or "Не удалось обработать файл.", "danger")
        return redirect(url_for("attendance.import_view", period_year=period_year, period_month_num=period_month_num))
    selected_building_id = request.values.get('building_id', type=int)
    sessions_q = AttendanceImportSession.query
    if selected_building_id:
        sessions_q = sessions_q.filter(AttendanceImportSession.building_id == selected_building_id)
    sessions = sessions_q.order_by(AttendanceImportSession.imported_at.desc()).limit(20).all()
    years, months = get_month_choices()
    school_days = _get_school_days_for_month(selected_month)
    buildings = Building.query.order_by(Building.name.asc()).all()
    return render_template(
        "attendance_import.html",
        sessions=sessions,
        default_month=default_month,
        default_year=selected_year,
        default_mon=selected_mon,
        years=years,
        months=months,
        school_days=school_days,
        selected_month=selected_month,
        buildings=buildings,
        selected_building_id=selected_building_id,
    )


@attendance_bp.route("/imports")
@login_required
def imports_registry():
    if getattr(current_user, "role", None) != "ADMIN":
        return redirect(url_for("main.dashboard"))
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20)
    year = request.args.get('year', type=int)
    month_num = request.args.get('month', type=int)
    building_id = request.args.get('building_id', type=int)

    query = AttendanceImportSession.query
    if year:
        query = query.filter(AttendanceImportSession.period_year == year)
    if month_num:
        query = query.filter(AttendanceImportSession.period_num == month_num)
    if building_id:
        query = query.filter(AttendanceImportSession.building_id == building_id)
    query = query.order_by(AttendanceImportSession.imported_at.desc(), AttendanceImportSession.id.desc())

    if str(per_page) == 'all':
        rows = query.all()
        total = len(rows)
        pagination = {
            'page': 1,
            'pages': 1,
            'total': total,
            'per_page': 'all',
            'has_prev': False,
            'has_next': False,
        }
        slice_rows = rows
    else:
        per_page_num = max(1, int(per_page or 20))
        pager = query.paginate(page=page, per_page=per_page_num, error_out=False)
        slice_rows = pager.items
        pagination = {
            'page': pager.page,
            'pages': pager.pages or 1,
            'total': pager.total,
            'per_page': per_page_num,
            'has_prev': pager.has_prev,
            'has_next': pager.has_next,
        }

    years, months = get_month_choices()
    buildings = Building.query.order_by(Building.name.asc()).all()
    return render_template(
        "attendance_imports.html",
        rows=slice_rows,
        pagination=pagination,
        years=years,
        months=months,
        buildings=buildings,
        selected_year=year,
        selected_month=month_num,
        selected_building_id=building_id,
    )


@attendance_bp.route('/imports/<int:session_id>/delete', methods=['POST'])
@login_required
def delete_import(session_id: int):
    if getattr(current_user, 'role', None) != 'ADMIN':
        return redirect(url_for('main.dashboard'))
    ok, msg = delete_import_session(session_id)
    if ok:
        cache.clear()
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('attendance.imports_registry'))


@attendance_bp.route("/analytics")
@login_required
def analytics():
    if not has_any_role("ADMIN", "CLASS_TEACHER", "SOCIAL_PEDAGOG"):
        return redirect(url_for("main.dashboard"))
    month = (request.args.get("month") or '').strip()
    if not month:
        year_arg = (request.args.get('period_year') or '').strip()
        mon_arg = (request.args.get('period_month_num') or '').strip()
        if year_arg and mon_arg:
            month = f'{year_arg}-{mon_arg}'
        else:
            month = get_default_month()
    grade = request.args.get('grade', type=int)
    class_id = request.args.get('class_id', type=int)
    building_id = request.args.get('building_id', type=int)
    mode = (request.args.get('mode') or 'school').strip()
    per_page = request.args.get('per_page', 20)
    class_page = request.args.get('class_page', 1, type=int)
    student_page = request.args.get('student_page', 1, type=int)
    sessions_page = request.args.get('sessions_page', 1, type=int)
    stats = build_month_analytics(
        month=month,
        user=current_user,
        grade=grade,
        class_id=class_id,
        building_id=building_id,
        mode=mode,
        class_page=class_page,
        student_page=student_page,
        sessions_page=sessions_page,
        per_page=per_page,
    )
    if not stats:
        empty_page = SimpleNamespace(items=[], page=1, per_page=per_page, total=0, pages=1, has_prev=False, has_next=False)
        stats = {
            "entries_count": 0,
            "lates_month": 0,
            "attendance_percent": 0,
            "avg_late_minutes": 0,
            "contingent_total": 0,
            "school_days_count": 0,
            "no_entry_count": 0,
            "no_exit_count": 0,
            "building_rows": [],
            "daily_rows": [],
            "chart_top_buildings": [],
            "chart_top_classes": [],
            "chart_top_students": [],
            "class_pagination": empty_page,
            "student_pagination": empty_page,
            "sessions_pagination": empty_page,
        }
    years, months = get_month_choices()
    year, mon = month.split('-')
    classes = _accessible_classes()
    if building_id:
        classes = [c for c in classes if getattr(c, 'building_id', None) == building_id]
    if grade is not None:
        classes = [c for c in classes if getattr(c, 'grade', None) == grade]
    classes = sorted(classes, key=lambda c: ((getattr(c, 'grade', 0) or 0), getattr(c, 'name', '')))
    buildings = Building.query.order_by(Building.name.asc()).all()
    return render_template(
        "attendance_analytics.html",
        stats=stats,
        month=month,
        selected_year=year,
        selected_mon=mon,
        years=years,
        months=months,
        grades=sorted({c.grade for c in classes if c.grade is not None}),
        classes=classes,
        buildings=buildings,
        selected_grade=grade,
        selected_class_id=class_id,
        selected_building_id=building_id,
        selected_mode=mode,
        per_page=per_page,
    )


@attendance_bp.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule_rules():
    if getattr(current_user, 'role', None) != 'ADMIN':
        return redirect(url_for('main.dashboard'))
    classes = _accessible_classes()
    classes_by_grade = _get_classes_by_grade(classes)
    current_year = _current_year()
    edit_id = request.args.get('edit', type=int)
    edit_rule = AttendanceScheduleRule.query.get(edit_id) if edit_id else None

    if request.method == 'POST':
        action = (request.form.get('action') or 'save').strip()
        rule_id = request.form.get('rule_id', type=int)
        rule = AttendanceScheduleRule.query.get(rule_id) if rule_id else None

        if action in {'delete', 'toggle'} and rule:
            if action == 'delete':
                db.session.delete(rule)
                db.session.commit()
                flash('Правило удалено.', 'success')
            else:
                rule.is_active = not rule.is_active
                db.session.commit()
                flash('Статус правила изменён.', 'success')
            return redirect(url_for('attendance.schedule_rules'))

        title = (request.form.get('title') or '').strip() or 'Начало занятий'
        grade = request.form.get('grade', type=int)
        school_class_id = request.form.get('school_class_id', type=int)
        selected_class_ids = [int(x) for x in request.form.getlist('class_ids') if str(x).isdigit()]
        start_time_raw = request.form.get('start_time') or '08:30'
        comment = (request.form.get('comment') or '').strip() or None

        try:
            start_time_value = datetime.strptime(start_time_raw, '%H:%M').time()
        except Exception:
            start_time_value = time(8, 30)

        if school_class_id and school_class_id not in selected_class_ids:
            selected_class_ids = [school_class_id]
        if not selected_class_ids and grade is not None:
            selected_class_ids = [c.id for c in classes_by_grade.get(grade, [])]
        if not selected_class_ids:
            flash('Нужно выбрать хотя бы один класс.', 'danger')
            return redirect(url_for('attendance.schedule_rules', edit=rule_id) if rule_id else url_for('attendance.schedule_rules'))

        conflicts = _find_conflicts(selected_class_ids, editing_rule_id=rule_id)
        if conflicts:
            conflict_text = '; '.join(
                f"{item['rule'].title}: {', '.join(c.name for c in item['classes'])}"
                for item in conflicts
            )
            flash(f'Конфликт правил. Уже существуют активные правила для классов: {conflict_text}', 'danger')
            return redirect(url_for('attendance.schedule_rules', edit=rule_id) if rule_id else url_for('attendance.schedule_rules'))

        if not rule:
            rule = AttendanceScheduleRule(academic_year_id=getattr(current_year, 'id', None), created_at=datetime.utcnow())
            db.session.add(rule)
        rule.title = title
        rule.grade = grade
        rule.school_class_id = school_class_id if school_class_id and len(selected_class_ids) == 1 else None
        rule.grade_from = grade
        rule.grade_to = grade
        rule.start_time = start_time_value
        rule.comment = comment
        rule.academic_year_id = getattr(current_year, 'id', None)
        rule.is_active = True
        rule.updated_at = datetime.utcnow()
        AttendanceScheduleRuleClass.query.filter_by(rule_id=rule.id).delete()
        db.session.flush()
        for class_id in selected_class_ids:
            db.session.add(AttendanceScheduleRuleClass(rule_id=rule.id, class_id=class_id))
        db.session.commit()
        flash('Настройка начала занятий сохранена.', 'success')
        return redirect(url_for('attendance.schedule_rules'))

    rows = [_serialize_rule(x) for x in AttendanceScheduleRule.query.order_by(AttendanceScheduleRule.updated_at.desc()).all()]
    return render_template(
        'attendance_start_times.html',
        rows=rows,
        classes=classes,
        classes_by_grade=classes_by_grade,
        edit_rule=edit_rule,
        edit_rule_class_ids=[x.id for x in _rule_classes(edit_rule)] if edit_rule else [],
        selected_grade=getattr(edit_rule, 'grade', None),
    )


@attendance_bp.route("/kpp")
@login_required
def kpp_screen():
    if getattr(current_user, "role", None) not in {"KPP", "ADMIN"}:
        return redirect(url_for("main.dashboard"))
    stats = build_attendance_dashboard_stats(current_user)
    return render_template("attendance_kpp.html", stats=stats)