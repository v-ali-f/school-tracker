from datetime import date

from app.services.teacher_mcko_service import (
    mcko_expires_at,
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
