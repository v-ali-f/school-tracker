from __future__ import annotations

from typing import Optional

from datetime import date, datetime
import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from app.core.extensions import db
from .models import (
    AcademicYear,
    SchoolClass,
    Child,
    ChildEnrollment,
    ChildEvent,
    ChildTransferHistory,
    ChildMovement,
)
from .roles import require_roles

transfers_bp = Blueprint("transfers", __name__, url_prefix="/transfers")


def _get_current_year():
    return AcademicYear.query.filter_by(is_current=True).first()


def _safe_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _calc_retention_until(year: Optional[AcademicYear]):
    if year and year.end_date:
        try:
            return year.end_date.replace(year=year.end_date.year + 7)
        except Exception:
            return None
    return None


def _split_class_name(name: str):
    raw = (name or "").strip().upper().replace(" ", "")
    m = re.match(r"^(\d{1,2})[- ]?(.+)$", raw)
    if not m:
        return None, None
    return int(m.group(1)), (m.group(2) or "").strip("-")


def _suggest_next_class(source_class: SchoolClass, target_year_id: Optional[int]):
    if not source_class or not target_year_id:
        return None
    grade = source_class.grade
    letter = (source_class.letter or "").strip()
    if grade is None:
        grade, letter = _split_class_name(source_class.name)
    if grade is None:
        return None

    candidates = (
        SchoolClass.query
        .filter(SchoolClass.academic_year_id == target_year_id)
        .order_by(SchoolClass.name.asc())
        .all()
    )
    wanted_grade = grade + 1
    for c in candidates:
        c_grade = c.grade if c.grade is not None else _split_class_name(c.name)[0]
        c_letter = (c.letter or _split_class_name(c.name)[1] or "").strip()
        if c_grade == wanted_grade and c_letter == letter:
            return c
    return None


def _close_enrollment(enrollment: ChildEnrollment, status: str, ended_dt: Optional[datetime] = None, note: Optional[str] = None):
    enrollment.status = status
    enrollment.ended_at = ended_dt or datetime.utcnow()
    if note:
        enrollment.note = note


def _record_transfer(*, child: Child, from_enrollment: Optional[ChildEnrollment], to_class: Optional[SchoolClass],
                     transfer_type: str, transfer_date: Optional[date], order_number: Optional[str] = None,
                     order_date: Optional[date] = None, comment: Optional[str] = None):
    hist = ChildTransferHistory(
        child_id=child.id,
        from_academic_year_id=from_enrollment.academic_year_id if from_enrollment else None,
        to_academic_year_id=to_class.academic_year_id if to_class else (from_enrollment.academic_year_id if from_enrollment else None),
        from_class_id=from_enrollment.school_class_id if from_enrollment else None,
        to_class_id=to_class.id if to_class else None,
        transfer_type=transfer_type,
        transfer_date=transfer_date,
        order_number=order_number,
        order_date=order_date,
        comment=comment,
        created_by=getattr(current_user, "id", None),
    )
    db.session.add(hist)
    ev_type = "PROMOTION"
    if transfer_type in {"EXPELLED", "ARCHIVED", "TRANSFERRED_OUT"}:
        ev_type = "EXPEL"
    elif transfer_type == "REPEAT":
        ev_type = "REPEAT"
    elif transfer_type == "CONDITIONAL":
        ev_type = "PROMOTION"
    db.session.add(ChildEvent(
        child_id=child.id,
        author_id=getattr(current_user, "id", None),
        event_type=ev_type,
        from_class=from_enrollment.school_class.name if from_enrollment and from_enrollment.school_class else None,
        to_class=to_class.name if to_class else None,
        promotion_kind=transfer_type,
        reason=comment,
        created_at=datetime.utcnow(),
    ))
    movement_type_map = {
        "PROMOTED": "transfer",
        "MANUAL": "transfer",
        "REPEAT": "repeat",
        "CONDITIONAL": "conditional",
        "EXPELLED": "leave",
        "ARCHIVED": "leave",
        "TRANSFERRED_OUT": "leave",
    }
    db.session.add(ChildMovement(
        child_id=child.id,
        academic_year_id=(to_class.academic_year_id if to_class else (from_enrollment.academic_year_id if from_enrollment else None)),
        movement_type=movement_type_map.get(transfer_type, "transfer"),
        movement_date=transfer_date or date.today(),
        from_class_id=from_enrollment.school_class_id if from_enrollment else None,
        to_class_id=to_class.id if to_class else None,
        reason=comment,
        order_number=order_number,
        created_by=getattr(current_user, "id", None),
    ))


def _active_enrollment_query(year_id=None):
    q = ChildEnrollment.query.filter(ChildEnrollment.ended_at.is_(None))
    if year_id:
        q = q.filter(ChildEnrollment.academic_year_id == year_id)
    return q


@transfers_bp.route("/")
@require_roles("ADMIN")
def index():
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    current_year = _get_current_year()
    target_year = years[0] if years else None
    if current_year and len(years) > 1:
        for y in years:
            if current_year.start_date and y.start_date and y.start_date > current_year.start_date:
                target_year = y
                break
    current_year_id = request.args.get("current_year_id", type=int) or (current_year.id if current_year else None)
    target_year_id = request.args.get("target_year_id", type=int) or (target_year.id if target_year else None)

    pending_count = 0
    promoted_count = 0
    archived_count = 0
    if current_year_id:
        pending_count = _active_enrollment_query(current_year_id).count()
        promoted_count = ChildTransferHistory.query.filter(ChildTransferHistory.from_academic_year_id == current_year_id).count()
        archived_count = ChildTransferHistory.query.filter(
            ChildTransferHistory.from_academic_year_id == current_year_id,
            ChildTransferHistory.transfer_type.in_(["EXPELLED", "ARCHIVED", "TRANSFERRED_OUT"]),
        ).count()

    return render_template(
        "transfers/index.html",
        years=years,
        current_year_id=current_year_id,
        target_year_id=target_year_id,
        pending_count=pending_count,
        promoted_count=promoted_count,
        archived_count=archived_count,
    )


@transfers_bp.route("/class", methods=["GET", "POST"])
@require_roles("ADMIN")
def class_to_class():
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    current_year = _get_current_year()
    from_year_id = request.values.get("from_year_id", type=int) or (current_year.id if current_year else None)
    to_year_id = request.values.get("to_year_id", type=int)
    if not to_year_id and years:
        ordered = sorted(years, key=lambda y: (y.start_date or date.min, y.name))
        if current_year in ordered:
            idx = ordered.index(current_year)
            if idx + 1 < len(ordered):
                to_year_id = ordered[idx + 1].id
    from_classes = SchoolClass.query.filter_by(academic_year_id=from_year_id).order_by(SchoolClass.name.asc()).all() if from_year_id else []
    to_classes = SchoolClass.query.filter_by(academic_year_id=to_year_id).order_by(SchoolClass.name.asc()).all() if to_year_id else []
    source_class_id = request.values.get("source_class_id", type=int)
    target_class_id = request.values.get("target_class_id", type=int)
    rows = []
    suggested_target = None
    if source_class_id:
        source_class = SchoolClass.query.get(source_class_id)
        if source_class and to_year_id and not target_class_id:
            suggested_target = _suggest_next_class(source_class, to_year_id)
            if suggested_target:
                target_class_id = suggested_target.id
        enrollments = (
            _active_enrollment_query(from_year_id)
            .filter(ChildEnrollment.school_class_id == source_class_id)
            .join(Child, Child.id == ChildEnrollment.child_id)
            .order_by(Child.last_name.asc(), Child.first_name.asc())
            .all()
        )
        for e in enrollments:
            rows.append({"enrollment": e, "child": e.child, "target_class_id": target_class_id})

    if request.method == "POST" and request.form.get("action") == "execute":
        target_class = SchoolClass.query.get_or_404(target_class_id)
        transfer_date = _safe_date(request.form.get("transfer_date")) or date.today()
        order_number = (request.form.get("order_number") or "").strip() or None
        order_date = _safe_date(request.form.get("order_date"))
        selected_ids = {int(x) for x in request.form.getlist("enrollment_ids") if str(x).isdigit()}
        changed = 0
        for e in _active_enrollment_query(from_year_id).filter(ChildEnrollment.school_class_id == source_class_id).all():
            if e.id not in selected_ids:
                continue
            _close_enrollment(e, "PROMOTED")
            new_enrollment = ChildEnrollment(
                child_id=e.child_id,
                academic_year_id=target_class.academic_year_id,
                school_class_id=target_class.id,
                status="ACTIVE",
                enrolled_at=datetime.utcnow(),
                transfer_order_number=order_number,
                transfer_order_date=order_date,
                note="Массовый перевод класс → класс",
            )
            db.session.add(new_enrollment)
            _record_transfer(child=e.child, from_enrollment=e, to_class=target_class,
                             transfer_type="PROMOTED", transfer_date=transfer_date,
                             order_number=order_number, order_date=order_date,
                             comment="Массовый перевод класс → класс")
            changed += 1
        db.session.commit()
        flash(f"Переведено учеников: {changed}", "success")
        return redirect(url_for("transfers.class_to_class", from_year_id=from_year_id, to_year_id=to_year_id, source_class_id=source_class_id, target_class_id=target_class_id))

    return render_template(
        "transfers/class_to_class.html",
        years=years,
        from_year_id=from_year_id,
        to_year_id=to_year_id,
        from_classes=from_classes,
        to_classes=to_classes,
        source_class_id=source_class_id,
        target_class_id=target_class_id,
        rows=rows,
        suggested_target=suggested_target,
    )


@transfers_bp.route("/parallel", methods=["GET", "POST"])
@require_roles("ADMIN")
def parallel_to_parallel():
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    current_year = _get_current_year()
    from_year_id = request.values.get("from_year_id", type=int) or (current_year.id if current_year else None)
    to_year_id = request.values.get("to_year_id", type=int)
    source_grade = request.values.get("source_grade", type=int)
    target_grade = request.values.get("target_grade", type=int)
    from_classes = SchoolClass.query.filter_by(academic_year_id=from_year_id).order_by(SchoolClass.name.asc()).all() if from_year_id else []
    to_classes = SchoolClass.query.filter_by(academic_year_id=to_year_id).order_by(SchoolClass.name.asc()).all() if to_year_id else []
    rows = []
    if source_grade:
        class_ids = [c.id for c in from_classes if c.grade == source_grade]
        if class_ids:
            enrollments = (
                _active_enrollment_query(from_year_id)
                .filter(ChildEnrollment.school_class_id.in_(class_ids))
                .join(Child, Child.id == ChildEnrollment.child_id)
                .order_by(Child.last_name.asc(), Child.first_name.asc())
                .all()
            )
            for e in enrollments:
                rows.append(e)

    if request.method == "POST":
        transfer_date = _safe_date(request.form.get("transfer_date")) or date.today()
        changed = 0
        for e in rows:
            target_class_id = request.form.get(f"target_class_{e.id}", type=int)
            if not target_class_id:
                continue
            target_class = SchoolClass.query.get(target_class_id)
            if not target_class:
                continue
            _close_enrollment(e, "PROMOTED")
            db.session.add(ChildEnrollment(
                child_id=e.child_id,
                academic_year_id=target_class.academic_year_id,
                school_class_id=target_class.id,
                status="ACTIVE",
                enrolled_at=datetime.utcnow(),
                note="Перевод параллели",
            ))
            _record_transfer(child=e.child, from_enrollment=e, to_class=target_class,
                             transfer_type="PROMOTED", transfer_date=transfer_date,
                             comment="Перевод параллели")
            changed += 1
        db.session.commit()
        flash(f"Распределено учеников: {changed}", "success")
        return redirect(url_for("transfers.parallel_to_parallel", from_year_id=from_year_id, to_year_id=to_year_id, source_grade=source_grade, target_grade=target_grade))

    return render_template("transfers/parallel_to_parallel.html", years=years, from_year_id=from_year_id,
                           to_year_id=to_year_id, source_grade=source_grade, target_grade=target_grade,
                           from_classes=from_classes, to_classes=to_classes, rows=rows)


@transfers_bp.route("/individual", methods=["GET", "POST"])
@require_roles("ADMIN")
def individual():
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    children = Child.query.order_by(Child.last_name.asc(), Child.first_name.asc()).all()
    year_id = request.values.get("year_id", type=int) or (_get_current_year().id if _get_current_year() else None)
    classes = SchoolClass.query.filter_by(academic_year_id=year_id).order_by(SchoolClass.name.asc()).all() if year_id else []
    if request.method == "POST":
        child_id = request.form.get("child_id", type=int)
        to_class_id = request.form.get("to_class_id", type=int)
        transfer_type = (request.form.get("transfer_type") or "MANUAL").upper()
        transfer_date = _safe_date(request.form.get("transfer_date")) or date.today()
        comment = (request.form.get("comment") or "").strip() or None
        child = Child.query.get_or_404(child_id)
        current_enrollment = _active_enrollment_query().filter_by(child_id=child.id).order_by(ChildEnrollment.id.desc()).first()
        target_class = SchoolClass.query.get_or_404(to_class_id)
        if current_enrollment:
            _close_enrollment(current_enrollment, transfer_type)
        db.session.add(ChildEnrollment(
            child_id=child.id,
            academic_year_id=target_class.academic_year_id,
            school_class_id=target_class.id,
            status="ACTIVE",
            enrolled_at=datetime.utcnow(),
            note=comment,
        ))
        _record_transfer(child=child, from_enrollment=current_enrollment, to_class=target_class,
                         transfer_type=transfer_type, transfer_date=transfer_date, comment=comment)
        db.session.commit()
        flash("Индивидуальный перевод сохранён", "success")
        return redirect(url_for("transfers.individual", year_id=target_class.academic_year_id))
    return render_template("transfers/individual.html", years=years, year_id=year_id, classes=classes, children=children)


@transfers_bp.route("/archive", methods=["GET", "POST"])
@require_roles("ADMIN")
def archive():
    children = Child.query.order_by(Child.last_name.asc(), Child.first_name.asc()).all()
    if request.method == "POST":
        child_id = request.form.get("child_id", type=int)
        action_type = (request.form.get("action_type") or "ARCHIVED").upper()
        comment = (request.form.get("comment") or "").strip() or None
        transfer_date = _safe_date(request.form.get("transfer_date")) or date.today()
        child = Child.query.get_or_404(child_id)
        current_enrollment = _active_enrollment_query().filter_by(child_id=child.id).order_by(ChildEnrollment.id.desc()).first()
        if current_enrollment:
            _close_enrollment(current_enrollment, action_type, note=comment)
        child.status = action_type
        child.archived_at = datetime.utcnow()
        _record_transfer(child=child, from_enrollment=current_enrollment, to_class=None,
                         transfer_type=action_type, transfer_date=transfer_date, comment=comment)
        db.session.commit()
        flash("Статус ученика обновлён", "success")
        return redirect(url_for("transfers.archive"))
    history = ChildTransferHistory.query.order_by(ChildTransferHistory.created_at.desc()).limit(50).all()
    return render_template("transfers/archive.html", children=children, history=history)
