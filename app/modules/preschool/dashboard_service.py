"""One calculation path for the preschool staff list and dashboard drilldowns."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_

from app.models_legacy import AcademicYear, TeacherAttestation, TeacherCourse, TeacherMckoResult, User
from app.services.teacher_professional_service import add_calendar_months
from app.services.teacher_mcko_service import mcko_expires_at
from app.services.teacher_attestation_service import attestation_overviews_for_teachers

from .models import PRESCHOOL_MCKO_TITLE, PreschoolBuildingStaff, PreschoolGroup, PreschoolGroupAssignment


ATTESTABLE_POSITIONS = {"SENIOR_EDUCATOR", "EDUCATOR", "PSYCHOLOGIST", "LOGOPEDIST", "DEFECTOLOGIST", "SOCIAL_PEDAGOG", "TUTOR", "SPECIALIST"}


@dataclass(frozen=True)
class StaffSnapshotRow:
    user: User
    building_names: tuple[str, ...]
    positions: tuple[str, ...]
    group_names: tuple[str, ...]
    mcko_state: str
    mcko_record: TeacherMckoResult | None
    attestation_state: str
    attestation_category: str | None
    attestation_record: TeacherAttestation | None
    attestation_due_at: date | None
    attestation_recommendation: str | None
    course_count: int
    course_hours: float


def academic_year_period(year: AcademicYear | None):
    if year is None:
        return None, None
    if year.start_date and year.end_date:
        return year.start_date, year.end_date
    try:
        first_year = int(year.name[:4])
        return date(first_year, 9, 1), date(first_year + 1, 8, 31)
    except (TypeError, ValueError):
        return year.start_date, year.end_date


def _within_year(course, year, start, end):
    if year is None:
        return True
    if course.academic_year_id == year.id:
        return True
    course_date = course.end_date or course.start_date
    return bool(course_date and (start is None or course_date >= start) and (end is None or course_date <= end))


def _effective(query, model, as_of):
    return query.filter(
        model.is_active.is_(True),
        or_(model.start_date.is_(None), model.start_date <= as_of),
        or_(model.end_date.is_(None), model.end_date >= as_of),
    )


def staff_snapshot(*, as_of: date, year: AcademicYear | None, allowed_building_ids: set[int],
                   building_id: int | None = None, position: str | None = None, warning_months: int = 6):
    building_ids = {building_id} if building_id else allowed_building_ids
    memberships = _effective(PreschoolBuildingStaff.query, PreschoolBuildingStaff, as_of).filter(
        PreschoolBuildingStaff.building_id.in_(building_ids or {-1}),
    ).all()
    if position:
        memberships = [row for row in memberships if row.position == position]
    by_user = {}
    for item in memberships:
        by_user.setdefault(item.user_id, []).append(item)
    if not by_user:
        return []
    users = {
        user.id: user for user in User.query.filter(
            User.id.in_(by_user), User.is_active_user.is_(True),
        ).all()
    }
    assignments = _effective(PreschoolGroupAssignment.query, PreschoolGroupAssignment, as_of).join(
        PreschoolGroup, PreschoolGroupAssignment.group_id == PreschoolGroup.id,
    ).filter(
        PreschoolGroupAssignment.user_id.in_(by_user),
        PreschoolGroupAssignment.building_id.in_(building_ids or {-1}),
        PreschoolGroup.is_archived.is_(False),
    )
    if year:
        assignments = assignments.filter(PreschoolGroupAssignment.academic_year_id == year.id)
    groups_by_user = {}
    for assignment in assignments.all():
        groups_by_user.setdefault(assignment.user_id, set()).add(assignment.group.name)
    mcko_by_user = {}
    for record in TeacherMckoResult.query.filter(
        TeacherMckoResult.teacher_id.in_(by_user),
        TeacherMckoResult.is_archived.is_(False),
        TeacherMckoResult.diagnostic_title == PRESCHOOL_MCKO_TITLE,
        or_(TeacherMckoResult.passed_at.is_(None), TeacherMckoResult.passed_at <= as_of),
    ).order_by(TeacherMckoResult.passed_at.desc().nullslast(), TeacherMckoResult.id.desc()).all():
        mcko_by_user.setdefault(record.teacher_id, record)
    attestation_overviews = attestation_overviews_for_teachers(by_user.keys(), as_of=as_of)
    course_start, course_end = academic_year_period(year)
    courses_by_user = {}
    for record in TeacherCourse.query.filter(
        TeacherCourse.teacher_id.in_(by_user), TeacherCourse.is_archived.is_(False),
    ).all():
        if _within_year(record, year, course_start, course_end):
            courses_by_user.setdefault(record.teacher_id, []).append(record)

    warning_date = add_calendar_months(as_of, warning_months)
    result = []
    for user_id, member_rows in by_user.items():
        user = users.get(user_id)
        if user is None:
            continue
        positions = {row.position for row in member_rows}
        mcko = mcko_by_user.get(user_id) if "EDUCATOR" in positions else None
        mcko_expiry = (mcko.expires_at or mcko_expires_at(mcko.passed_at)) if mcko else None
        if "EDUCATOR" not in positions:
            mcko_state = "NOT_APPLICABLE"
        elif mcko is None or mcko.passed_at is None:
            mcko_state = "MISSING"
        elif mcko_expiry is None or mcko_expiry < as_of:
            mcko_state = "EXPIRED"
        elif mcko_expiry <= warning_date:
            mcko_state = "EXPIRING"
        else:
            mcko_state = "VALID"
        overview = attestation_overviews.get(user_id) if positions & ATTESTABLE_POSITIONS else None
        attestation = overview.record if overview else None
        due_at = overview.effective_valid_until if overview else None
        if not positions & ATTESTABLE_POSITIONS:
            attestation_state = "NOT_APPLICABLE"
        elif attestation is None:
            if due_at is None:
                attestation_state = "NO_HIRE_DATE"
            elif due_at <= as_of:
                attestation_state = "DUE"
            elif due_at <= warning_date:
                attestation_state = "UPCOMING"
            else:
                attestation_state = "MISSING"
        else:
            if overview.status == "INDEFINITE":
                attestation_state = "INDEFINITE"
            elif overview.status == "INCOMPLETE" or due_at is None:
                attestation_state = "INCOMPLETE"
            elif due_at < as_of:
                attestation_state = "EXPIRED"
            elif due_at <= warning_date:
                attestation_state = "EXPIRING"
            else:
                attestation_state = "VALID"
        if attestation_state == "DUE":
            recommendation = "Предложить проверить возможность аттестации на соответствие должности"
        elif attestation_state == "UPCOMING":
            recommendation = "Подготовить проверку к окончанию двух лет работы"
        elif attestation_state == "EXPIRED":
            recommendation = "Проверить необходимость повторной аттестации"
        elif attestation_state == "EXPIRING":
            recommendation = "Запланировать проверку срока аттестации"
        elif attestation_state == "NO_HIRE_DATE":
            recommendation = "Уточнить дату приёма на работу"
        else:
            recommendation = None
        courses = courses_by_user.get(user_id, [])
        result.append(StaffSnapshotRow(
            user=user,
            building_names=tuple(sorted({row.building.name for row in member_rows})),
            positions=tuple(sorted(positions)),
            group_names=tuple(sorted(groups_by_user.get(user_id, set()))),
            mcko_state=mcko_state,
            mcko_record=mcko,
            attestation_state=attestation_state,
            attestation_category=attestation.category if attestation else None,
            attestation_record=attestation,
            attestation_due_at=due_at,
            attestation_recommendation=recommendation,
            course_count=len(courses),
            course_hours=sum(float(course.hours or 0) for course in courses),
        ))
    return sorted(result, key=lambda row: (row.user.fio or row.user.username).casefold())


def metric_rows(rows):
    return {
        "staff_total": rows,
        "mcko_total": [row for row in rows if row.mcko_state != "NOT_APPLICABLE"],
        "mcko_valid": [row for row in rows if row.mcko_state in {"VALID", "EXPIRING"}],
        "mcko_missing": [row for row in rows if row.mcko_state == "MISSING"],
        "mcko_expiring": [row for row in rows if row.mcko_state == "EXPIRING"],
        "mcko_expired": [row for row in rows if row.mcko_state == "EXPIRED"],
        "attest_first": [row for row in rows if row.attestation_category == "FIRST"],
        "attest_highest": [row for row in rows if row.attestation_category == "HIGHEST"],
        "attest_position": [row for row in rows if row.attestation_category == "POSITION_COMPLIANCE"],
        "attest_missing": [row for row in rows if row.attestation_state in {"MISSING", "DUE", "UPCOMING", "NO_HIRE_DATE"}],
        "attest_due": [row for row in rows if row.attestation_state == "DUE"],
        "attest_upcoming": [row for row in rows if row.attestation_state == "UPCOMING"],
        "attest_no_hire_date": [row for row in rows if row.attestation_state == "NO_HIRE_DATE"],
        "attest_expiring": [row for row in rows if row.attestation_state == "EXPIRING"],
        "attest_expired": [row for row in rows if row.attestation_state == "EXPIRED"],
        "course_with": [row for row in rows if row.course_count],
        "course_without": [row for row in rows if not row.course_count],
        "course_hours": [row for row in rows if row.course_hours],
    }
