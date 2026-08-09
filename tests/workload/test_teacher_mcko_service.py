from datetime import date
from types import SimpleNamespace

from app.services.teacher_mcko_service import (
    mcko_expires_at,
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
