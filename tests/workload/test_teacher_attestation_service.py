from datetime import date
from types import SimpleNamespace

from app.core.extensions import db
from app.models import TeacherAttestation, User
from app.services.teacher_attestation_service import (
    attestation_overviews_for_teachers,
    attestation_view,
    position_compliance_due_at,
)


def _record(
    *,
    category="FIRST",
    decision_date=date(2024, 1, 15),
    valid_until=None,
    is_indefinite=False,
):
    return SimpleNamespace(
        category=category,
        decision_date=decision_date,
        valid_until=valid_until,
        is_indefinite=is_indefinite,
        entry_source="ADMINISTRATION",
    )


def test_position_compliance_is_due_two_calendar_years_after_basis_date():
    assert position_compliance_due_at(date(2024, 2, 29)) == date(2026, 2, 28)
    assert position_compliance_due_at(
        date(2020, 1, 1),
        last_decision_date=date(2025, 5, 20),
    ) == date(2027, 5, 20)


def test_attestation_supports_indefinite_and_fixed_categories():
    indefinite = attestation_view(
        _record(is_indefinite=True),
        as_of=date(2026, 1, 15),
    )
    warning = attestation_view(
        _record(valid_until=date(2026, 7, 15)),
        as_of=date(2026, 1, 15),
    )
    active = attestation_view(
        _record(valid_until=date(2026, 7, 16)),
        as_of=date(2026, 1, 15),
    )
    expired = attestation_view(
        _record(valid_until=date(2026, 1, 14)),
        as_of=date(2026, 1, 15),
    )

    assert indefinite.status == "INDEFINITE"
    assert warning.status == "EXPIRING_SOON"
    assert active.status == "ACTIVE"
    assert expired.status == "EXPIRED"


def test_position_compliance_uses_two_year_term_when_end_date_is_missing():
    view = attestation_view(
        _record(
            category="POSITION_COMPLIANCE",
            decision_date=date(2025, 3, 10),
        ),
        as_of=date(2026, 3, 10),
    )

    assert view.effective_valid_until == date(2027, 3, 10)
    assert view.status == "ACTIVE"


def test_active_category_suppresses_employment_compliance_warning(
    app,
    make_user,
):
    teacher_id = make_user("TEACHER")
    warning_teacher_id = make_user("TEACHER")
    missing_date_teacher_id = make_user("TEACHER")
    with app.app_context():
        teacher = db.session.get(User, teacher_id)
        teacher.employment_start_date = date(2020, 9, 1)
        warning_teacher = db.session.get(User, warning_teacher_id)
        warning_teacher.employment_start_date = date(2024, 10, 1)
        db.session.add(TeacherAttestation(
            teacher_id=teacher_id,
            category="FIRST",
            decision_date=date(2025, 5, 20),
            valid_until=date(2028, 5, 20),
            entry_source="ADMINISTRATION",
        ))
        db.session.commit()

        overviews = attestation_overviews_for_teachers(
            [teacher_id, warning_teacher_id, missing_date_teacher_id],
            as_of=date(2026, 8, 9),
        )

        assert overviews[teacher_id].status == "ACTIVE"
        assert overviews[teacher_id].category_code == "FIRST"
        assert overviews[teacher_id].basis_label == "Действующая квалификационная категория"
        assert overviews[warning_teacher_id].status == "EXPIRING_SOON"
        assert overviews[warning_teacher_id].category_code == "MISSING"
        assert overviews[warning_teacher_id].category_label == "—"
        assert overviews[warning_teacher_id].effective_valid_until == date(2026, 10, 1)
        assert overviews[missing_date_teacher_id].status == "INCOMPLETE"
        assert overviews[missing_date_teacher_id].status_label == "Не указана дата приёма"
        assert overviews[missing_date_teacher_id].category_code == "MISSING"
        assert overviews[missing_date_teacher_id].category_label == "—"
