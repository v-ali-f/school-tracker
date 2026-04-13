# app/ovz_rules.py

OVZ_LEVELS = [("NOO", "НОО (1–4)"), ("OOO", "ООО (5–9)"), ("SOO", "СОО (10–11)")]

OVZ_NOZOLOGIES = [
    ("ZPR", "ЗПР"),
    ("TNR", "ТНР"),
    ("RAS", "РАС"),
    ("NODA", "НОДА"),
    ("SLUH", "Нарушение слуха"),
    ("ZREN", "Нарушение зрения"),
    ("INT", "Интеллектуальные нарушения"),
    ("TMNR", "ТМНР"),
]

# допустимые варианты по (уровень, нозология)
# Собрано по логике ФГОС ОВЗ:
_ALLOWED = {
    ("NOO", "ZPR"): [1, 2],
    ("NOO", "TNR"): [1, 2],
    ("NOO", "NODA"): [1, 2, 3, 4],
    ("NOO", "RAS"): [1, 2, 3, 4],
    ("NOO", "SLUH"): [1, 2, 3, 4],
    ("NOO", "ZREN"): [1, 2, 3, 4],
    ("NOO", "INT"): [1, 2, 3, 4],
    ("NOO", "TMNR"): [3, 4],

    ("OOO", "ZPR"): [1, 2],
    ("OOO", "TNR"): [1, 2],
    ("OOO", "NODA"): [1, 2, 3],
    ("OOO", "RAS"): [1, 2, 3, 4],
    ("OOO", "SLUH"): [1, 2, 3, 4],
    ("OOO", "ZREN"): [1, 2, 3, 4],
    ("OOO", "INT"): [1, 2, 3, 4],
    ("OOO", "TMNR"): [3, 4],

    ("SOO", "ZPR"): [1, 2],
    ("SOO", "TNR"): [1, 2],
    ("SOO", "NODA"): [1, 2],
    ("SOO", "RAS"): [1, 2, 3],
    ("SOO", "SLUH"): [1, 2, 3],
    ("SOO", "ZREN"): [1, 2, 3],
    ("SOO", "INT"): [1, 2, 3, 4],
    ("SOO", "TMNR"): [3, 4],
}

def allowed_variants(level: str, nosology: str):
    if not level or not nosology:
        return []
    return _ALLOWED.get((level, nosology), [])

def is_allowed(level: str, nosology: str, variant: int):
    return variant in allowed_variants(level, nosology)
