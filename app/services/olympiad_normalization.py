from __future__ import annotations

from typing import Optional

STAGE_LABELS = {
    "school": "Школьный этап",
    "municipal": "Муниципальный этап",
    "regional": "Региональный этап",
    "final": "Заключительный этап",
    "unknown": "Не определён",
}

STAGE_BADGES = {
    "school": "ШЭ",
    "municipal": "МЭ",
    "regional": "РЭ",
    "final": "ЗЭ",
    "unknown": "?",
}

STATUS_LABELS = {
    "winner": "Победитель",
    "prize": "Призёр",
    "participant": "Участник",
    "out_of_competition": "Вне конкурса",
    "annulled": "Аннулировано",
    "unknown": "Не определено",
}

ANNULLED_MARKERS = [
    "аннулирован",
    "аннулирована",
    "аннуляция",
    "работа аннулирована",
    "дисквалификац",
    "дисквалифицирован",
    "нарушение",
    "использование справочных материалов",
    "письменных заметок",
    "средств хранения и передачи информации",
    "работа аннулирована по решению жюри",
]


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().lower().replace("ё", "е").split())


def normalize_olympiad_stage(stage: object) -> str:
    text = _norm(stage)
    if not text:
        return "unknown"
    if text in {"school", "шэ"} or "школь" in text:
        return "school"
    if text in {"municipal", "мэ"} or "муницип" in text:
        return "municipal"
    if text in {"regional", "рэ"} or "регион" in text:
        return "regional"
    if text in {"final", "зэ"} or "заключ" in text or "финал" in text:
        return "final"
    return "unknown"


def stage_label(stage_group: Optional[str], fallback: object = None) -> str:
    group = stage_group or normalize_olympiad_stage(fallback)
    return STAGE_LABELS.get(group, str(fallback or "Не определён"))


def stage_badge(stage_group: Optional[str], fallback: object = None) -> str:
    group = stage_group or normalize_olympiad_stage(fallback)
    return STAGE_BADGES.get(group, "?")


def normalize_olympiad_status(status: object, reason: object = None) -> str:
    text = _norm(status)
    reason_text = _norm(reason)
    combined = f"{text} {reason_text}".strip()
    if not combined:
        return "unknown"
    if any(marker in combined for marker in ANNULLED_MARKERS):
        return "annulled"
    if "вне конкурса" in combined or "вне зачета" in combined or "вне зачёта" in combined:
        return "out_of_competition"
    if "побед" in text:
        return "winner"
    if "приз" in text:
        return "prize"
    if "участ" in text:
        return "participant"
    return "unknown"


def status_label(status_group: Optional[str], fallback: object = None) -> str:
    group = status_group or normalize_olympiad_status(fallback)
    return STATUS_LABELS.get(group, str(fallback or "Не определено"))


def is_counted_result(status_group: Optional[str]) -> bool:
    return status_group not in {"annulled", "out_of_competition"}


def enrich_olympiad_result(result) -> None:
    raw_status = getattr(result, "status_original", None) or getattr(result, "status", None)
    group = normalize_olympiad_status(raw_status, getattr(result, "reason", None))
    result.status_original = raw_status
    result.status_group = group
    result.status = status_label(group, raw_status)
    result.is_annulled = group == "annulled"
    result.stage_group = normalize_olympiad_stage(getattr(result, "stage", None))
