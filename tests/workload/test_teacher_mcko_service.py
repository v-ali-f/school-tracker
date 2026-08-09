from datetime import date
from types import SimpleNamespace

from app.core.extensions import db
from app.models import EducationActivity, TeacherMckoResult
from app.services.teacher_mcko_service import (
    mcko_expires_at,
    mcko_overviews_for_teachers,
    mcko_result_view,
    normalize_mcko_level,
)


def test_mcko_expiration_is_three_calendar_years():
    assert mcko_expires_at(date(2024, 2, 29)) == date(2027, 2, 28)
    assert mcko_expires_at(date(2024, 5, 26)) == date(2027, 5, 26)


def test_mcko_levels_are_normalized_to_four_codes():
    assert normalize_mcko_level("Ниже базового") == "BELOW_BASIC"
    assert normalize_mcko_level("Базовый") == "BASIC"
    assert normalize_mcko_level("Высокий") == "HIGH"
    assert normalize_mcko_level("Экспертный") == "EXPERT"
    assert normalize_mcko_level("неизвестный") is None


def _record(*, passed_at, source="ADMINISTRATION"):
    return SimpleNamespace(
        passed_at=passed_at,
        expires_at=None,
        education_activity=SimpleNamespace(name="Математика"),
        subject=None,
        level="HIGH",
        entry_source=source,
        certificate_number="МК-123",
        result_text=None,
    )


def test_mcko_status_warns_six_months_before_expiration():
    warning = mcko_result_view(
        _record(passed_at=date(2023, 7, 15)),
        as_of=date(2026, 1, 15),
    )
    active = mcko_result_view(
        _record(passed_at=date(2023, 7, 16)),
        as_of=date(2026, 1, 15),
    )
    expired = mcko_result_view(
        _record(passed_at=date(2022, 1, 14)),
        as_of=date(2026, 1, 15),
    )

    assert warning.status == "EXPIRING_SOON"
    assert warning.remaining_days == 181
    assert active.status == "ACTIVE"
    assert expired.status == "EXPIRED"
    assert warning.source_label == "Внесено администрацией"


def test_overview_uses_latest_result_per_subject_and_includes_missing_teacher(
    app,
    make_user,
):
    teacher_id = make_user("TEACHER")
    missing_teacher_id = make_user("TEACHER")
    with app.app_context():
        activity = EducationActivity(
            code="overview-mathematics",
            name="Математика",
            activity_kind="SUBJECT",
            is_global=True,
            is_active=True,
        )
        db.session.add(activity)
        db.session.flush()
        db.session.add_all([
            TeacherMckoResult(
                teacher_id=teacher_id,
                education_activity_id=activity.id,
                passed_at=date(2021, 5, 20),
                level="BASIC",
            ),
            TeacherMckoResult(
                teacher_id=teacher_id,
                education_activity_id=activity.id,
                passed_at=date(2025, 5, 20),
                level="HIGH",
            ),
        ])
        db.session.commit()

        overviews = mcko_overviews_for_teachers(
            [teacher_id, missing_teacher_id],
            as_of=date(2026, 8, 9),
        )

        assert overviews[teacher_id].status == "ACTIVE"
        assert len(overviews[teacher_id].latest_results) == 1
        assert overviews[teacher_id].latest_results[0].level_code == "HIGH"
        assert overviews[missing_teacher_id].status == "MISSING"
        assert overviews[missing_teacher_id].valid_results == ()
