"""Preschool staff cabinet backed by the shared school professional records."""

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.core.extensions import db
from app.models_legacy import Building, TeacherAttestation, TeacherCourse, TeacherMckoResult, User
from app.services.teacher_attestation_service import ATTESTATION_CATEGORY_LABELS, position_compliance_due_at
from app.services.teacher_mcko_service import MCKO_LEVEL_LABELS, mcko_expires_at, mcko_result_view, normalize_mcko_level
from app.services.teacher_professional_audit_service import CHANGE_CREATED, CHANGE_UPDATED, record_professional_change
from app.services.teacher_professional_service import professional_entry_source

from .access import CHIEF_EDUCATOR, assigned_building_ids, assigned_group_ids, is_responsible, managed_building_ids, role_codes
from .models import PRESCHOOL_MCKO_TITLE, PreschoolAchievement, PreschoolBuildingStaff, PreschoolChild, PreschoolGroup, PreschoolGroupAssignment, PreschoolProfileChange


ATTESTABLE_ROLES = {"SENIOR_EDUCATOR", "EDUCATOR", "PSYCHOLOGIST", "LOGOPEDIST", "DEFECTOLOGIST", "SOCIAL_PEDAGOG", "TUTOR", "SPECIALIST"}
ROLE_LABELS = {
    "SENIOR_EDUCATOR": "Старший воспитатель", "EDUCATOR": "Воспитатель",
    "ASSISTANT_EDUCATOR": "Помощник воспитателя", "PSYCHOLOGIST": "Педагог-психолог",
    "LOGOPEDIST": "Учитель-логопед", "DEFECTOLOGIST": "Учитель-дефектолог",
    "SOCIAL_PEDAGOG": "Социальный педагог", "TUTOR": "Тьютор", "SPECIALIST": "Специалист",
}


def _preschool_employee(user):
    return bool(PreschoolBuildingStaff.query.join(Building).filter(
        PreschoolBuildingStaff.user_id == user.id,
        PreschoolBuildingStaff.is_active.is_(True),
        Building.is_preschool.is_(True),
    ).first())


def _can_view_person(user):
    if user.id == current_user.id:
        return True
    if not _preschool_employee(user):
        return False
    if role_codes() & {"ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR"}:
        return True
    return bool(assigned_building_ids(user) & managed_building_ids())


def _can_edit_person(user):
    return user.id == current_user.id or "ADMIN" in role_codes()


def _can_attest_person(user):
    return bool(
        _preschool_employee(user)
        and role_codes(user) & ATTESTABLE_ROLES
        and ("ADMIN" in role_codes() or is_responsible(current_user, CHIEF_EDUCATOR))
    )


def _date_value(name, *, required=False):
    raw = (request.form.get(name) or "").strip()
    if not raw:
        if required:
            raise ValueError("Укажите дату.")
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("Укажите корректную дату.") from exc


def _person_or_404(user_id):
    user = db.session.get(User, user_id)
    if user is None or not _can_view_person(user):
        abort(404 if user is None else 403)
    return user


def register_routes(bp):
    @bp.get("/cabinet")
    def cabinet():
        return redirect(url_for("preschool.staff_profile", user_id=current_user.id))

    @bp.get("/staff/<int:user_id>/profile")
    def staff_profile(user_id):
        user = _person_or_404(user_id)
        buildings = PreschoolBuildingStaff.query.join(Building).filter(
            PreschoolBuildingStaff.user_id == user.id,
            PreschoolBuildingStaff.is_active.is_(True),
            Building.is_preschool.is_(True),
        ).all()
        groups = PreschoolGroupAssignment.query.filter_by(user_id=user.id, is_active=True).all()
        mcko = TeacherMckoResult.query.filter_by(teacher_id=user.id, is_archived=False).order_by(
            TeacherMckoResult.passed_at.desc().nullslast(), TeacherMckoResult.id.desc(),
        ).all()
        courses = TeacherCourse.query.filter_by(teacher_id=user.id, is_archived=False).order_by(
            TeacherCourse.end_date.desc().nullslast(), TeacherCourse.id.desc(),
        ).all()
        attestations = TeacherAttestation.query.filter_by(teacher_id=user.id, is_archived=False).order_by(
            TeacherAttestation.decision_date.desc(), TeacherAttestation.id.desc(),
        ).all()
        achievements = PreschoolAchievement.query.filter_by(teacher_id=user.id, is_archived=False).order_by(
            PreschoolAchievement.event_date.desc().nullslast(), PreschoolAchievement.id.desc(),
        ).all()
        own_group_ids = assigned_group_ids(user)
        own_groups = PreschoolGroup.query.filter(PreschoolGroup.id.in_(own_group_ids or {-1})).order_by(PreschoolGroup.name).all()
        own_children = PreschoolChild.query.filter(
            PreschoolChild.group_id.in_(own_group_ids or {-1}), PreschoolChild.status == "active",
        ).order_by(PreschoolChild.last_name, PreschoolChild.first_name).all()
        return render_template(
            "preschool/cabinet.html", person=user, buildings=buildings, groups=groups,
            mcko=[mcko_result_view(row) for row in mcko], courses=courses,
            attestations=attestations, achievements=achievements,
            own_groups=own_groups, own_children=own_children,
            can_edit=_can_edit_person(user), can_edit_profile=user.id == current_user.id,
            can_attest=_can_attest_person(user), mcko_levels=MCKO_LEVEL_LABELS,
            attestation_categories=ATTESTATION_CATEGORY_LABELS,
            position_compliance_due_at=position_compliance_due_at,
            role_labels=ROLE_LABELS,
            preschool_mcko_title=PRESCHOOL_MCKO_TITLE,
        )

    @bp.post("/cabinet/profile")
    def profile_update():
        user = current_user
        fields = ("last_name", "first_name", "middle_name", "phone", "email")
        old_values = {field: getattr(user, field) for field in fields}
        values = {field: (request.form.get(field) or "").strip() or None for field in fields}
        if not values["last_name"] or not values["first_name"]:
            abort(400)
        if any(len(values[field] or "") > 120 for field in fields):
            abort(400)
        if values["email"] and ("@" not in values["email"] or len(values["email"]) > 120):
            abort(400)
        for field, value in values.items():
            setattr(user, field, value)
        db.session.add(PreschoolProfileChange(
            user_id=user.id, changed_by_user_id=user.id,
            old_values=old_values, new_values=values,
        ))
        db.session.commit()
        flash("Личные сведения обновлены.", "success")
        return redirect(url_for("preschool.staff_profile", user_id=user.id))

    @bp.post("/staff/<int:user_id>/mcko")
    def mcko_save(user_id):
        user = _person_or_404(user_id)
        if not _can_edit_person(user) or "EDUCATOR" not in role_codes(user):
            abort(403)
        record_id = request.form.get("record_id", type=int)
        record = db.session.get(TeacherMckoResult, record_id) if record_id else None
        if record_id and (record is None or record.teacher_id != user.id or record.is_archived or record.diagnostic_title != PRESCHOOL_MCKO_TITLE):
            abort(404)
        try:
            passed_at = _date_value("passed_at", required=True)
            expires_at = _date_value("expires_at") or mcko_expires_at(passed_at)
        except ValueError:
            abort(400)
        level = normalize_mcko_level(request.form.get("level"))
        if level is None or expires_at < passed_at:
            abort(400)
        action = CHANGE_UPDATED if record else CHANGE_CREATED
        if record is None:
            record = TeacherMckoResult(
                teacher_id=user.id, diagnostic_title=PRESCHOOL_MCKO_TITLE,
                entry_source=professional_entry_source(teacher_id=user.id, actor_id=current_user.id),
                created_by_user_id=current_user.id,
            )
            db.session.add(record)
        record.passed_at = passed_at
        record.expires_at = expires_at
        record.level = level
        record.result_text = (request.form.get("result_text") or "").strip() or None
        record.certificate_number = (request.form.get("certificate_number") or "").strip() or None
        record.updated_by_user_id = current_user.id
        record_professional_change(record, change_kind=action, actor_id=current_user.id)
        db.session.commit()
        flash("Результат диагностики сохранён в общем реестре.", "success")
        return redirect(url_for("preschool.staff_profile", user_id=user.id))

    @bp.post("/staff/<int:user_id>/course")
    def course_save(user_id):
        user = _person_or_404(user_id)
        if not _can_edit_person(user):
            abort(403)
        record_id = request.form.get("record_id", type=int)
        record = db.session.get(TeacherCourse, record_id) if record_id else None
        if record_id and (record is None or record.teacher_id != user.id or record.is_archived):
            abort(404)
        title = (request.form.get("title") or "").strip()
        if not title or len(title) > 255:
            abort(400)
        try:
            start_date = _date_value("start_date")
            end_date = _date_value("end_date")
        except ValueError:
            abort(400)
        if start_date and end_date and start_date > end_date:
            abort(400)
        raw_hours = (request.form.get("hours") or "").strip().replace(",", ".")
        try:
            hours = float(raw_hours) if raw_hours else None
        except ValueError:
            abort(400)
        if hours is not None and hours <= 0:
            abort(400)
        number = (request.form.get("document_number") or "").strip() or None
        candidates = TeacherCourse.query.filter_by(teacher_id=user.id, is_archived=False).all()
        if any(item.id != record_id and item.title.casefold() == title.casefold()
               and item.start_date == start_date and item.end_date == end_date
               and (item.document_number or "").casefold() == (number or "").casefold() for item in candidates):
            abort(409)
        action = CHANGE_UPDATED if record else CHANGE_CREATED
        if record is None:
            record = TeacherCourse(
                teacher_id=user.id,
                entry_source=professional_entry_source(teacher_id=user.id, actor_id=current_user.id),
                created_by_user_id=current_user.id,
            )
            db.session.add(record)
        record.title = title
        record.provider = (request.form.get("provider") or "").strip() or None
        record.hours = hours
        record.start_date = start_date
        record.end_date = end_date
        record.document_title = (request.form.get("document_title") or "").strip() or None
        record.document_number = number
        record.notes = (request.form.get("notes") or "").strip() or None
        record.updated_by_user_id = current_user.id
        record_professional_change(record, change_kind=action, actor_id=current_user.id)
        db.session.commit()
        flash("Курс сохранён в общем реестре.", "success")
        return redirect(url_for("preschool.staff_profile", user_id=user.id))

    @bp.post("/staff/<int:user_id>/achievement")
    def achievement_save(user_id):
        user = _person_or_404(user_id)
        if not _can_edit_person(user):
            abort(403)
        kind = (request.form.get("kind") or "").strip().upper()
        name = (request.form.get("event_name") or "").strip()
        if kind not in {"CHILD", "PEDAGOGICAL"} or not name or len(name) > 255:
            abort(400)
        child_id = request.form.get("child_id", type=int) if kind == "CHILD" else None
        group_id = request.form.get("group_id", type=int) if kind == "CHILD" else None
        child = db.session.get(PreschoolChild, child_id) if child_id else None
        if child_id and child is None:
            abort(400)
        if child and group_id and child.group_id != group_id:
            abort(400)
        group_id = group_id or (child.group_id if child else None)
        if kind == "CHILD":
            if not group_id or db.session.get(PreschoolGroup, group_id) is None:
                abort(400)
            if user.id == current_user.id and group_id not in assigned_group_ids(user):
                abort(403)
        try:
            event_date = _date_value("event_date")
        except ValueError:
            abort(400)
        record_id = request.form.get("record_id", type=int)
        record = db.session.get(PreschoolAchievement, record_id) if record_id else None
        if record_id and (record is None or record.teacher_id != user.id or record.is_archived):
            abort(404)
        if record is None:
            record = PreschoolAchievement(teacher_id=user.id, created_by_user_id=current_user.id)
            db.session.add(record)
        record.kind = kind
        record.child_id = child_id
        record.group_id = group_id
        record.event_name = name
        record.level = (request.form.get("level") or "").strip() or None
        record.organizer = (request.form.get("organizer") or "").strip() or None
        record.event_date = event_date
        record.result = (request.form.get("result") or "").strip() or None
        record.award = (request.form.get("award") or "").strip() or None
        record.document = (request.form.get("document") or "").strip() or None
        record.updated_by_user_id = current_user.id
        db.session.commit()
        flash("Достижение сохранено.", "success")
        return redirect(url_for("preschool.staff_profile", user_id=user.id))

    @bp.post("/staff/<int:user_id>/attestation")
    def attestation_save(user_id):
        user = _person_or_404(user_id)
        if not _can_attest_person(user):
            abort(403)
        category = (request.form.get("category") or "").strip().upper()
        if category not in ATTESTATION_CATEGORY_LABELS:
            abort(400)
        try:
            decision_date = _date_value("decision_date", required=True)
            valid_until = _date_value("valid_until")
        except ValueError:
            abort(400)
        indefinite = category in {"FIRST", "HIGHEST"} and request.form.get("is_indefinite") == "1"
        if category == "POSITION_COMPLIANCE":
            valid_until = position_compliance_due_at(None, last_decision_date=decision_date)
        elif indefinite:
            valid_until = None
        elif valid_until is None:
            abort(400)
        if valid_until and valid_until < decision_date:
            abort(400)
        record_id = request.form.get("record_id", type=int)
        record = db.session.get(TeacherAttestation, record_id) if record_id else None
        if record_id and (record is None or record.teacher_id != user.id or record.is_archived):
            abort(404)
        action = CHANGE_UPDATED if record else CHANGE_CREATED
        if record is None:
            record = TeacherAttestation(
                teacher_id=user.id,
                entry_source=professional_entry_source(teacher_id=user.id, actor_id=current_user.id),
                created_by_user_id=current_user.id,
            )
            db.session.add(record)
        record.category = category
        record.position_title = (request.form.get("position_title") or "").strip() or None
        record.decision_date = decision_date
        record.valid_until = valid_until
        record.is_indefinite = indefinite
        record.order_number = (request.form.get("order_number") or "").strip() or None
        record.updated_by_user_id = current_user.id
        record_professional_change(record, change_kind=action, actor_id=current_user.id)
        db.session.commit()
        flash("Аттестация сохранена в общем реестре.", "success")
        return redirect(url_for("preschool.staff_profile", user_id=user.id))
