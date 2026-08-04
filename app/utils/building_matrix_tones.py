BUILDING_MATRIX_TONE_CHOICES = (
    (0, "Без заливки"),
    (1, "Голубой"),
    (2, "Зелёный"),
    (3, "Жёлтый"),
    (4, "Сиреневый"),
    (5, "Розовый"),
)

BUILDING_MATRIX_TONE_VALUES = {
    value
    for value, _label in BUILDING_MATRIX_TONE_CHOICES
}


def normalize_building_matrix_tone(value):
    try:
        tone = int(value)
    except (TypeError, ValueError):
        return 0
    return tone if tone in BUILDING_MATRIX_TONE_VALUES else 0


def building_matrix_tone(building):
    if building is None:
        return 0
    return normalize_building_matrix_tone(
        getattr(building, "matrix_tone", 0)
    )


__all__ = [
    "BUILDING_MATRIX_TONE_CHOICES",
    "building_matrix_tone",
    "normalize_building_matrix_tone",
]
