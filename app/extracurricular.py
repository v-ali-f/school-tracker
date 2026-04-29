"""Дополнительное образование: матчинг учеников с выгрузкой заявлений на кружки.

Источник — JSON-кеш `data/do_index.json`, собранный из xlsx-выгрузки
«Реестр учеников по заявлениям на кружки май 2025 - апрель 2026».

Матчинг с Child делается по паре (нормализованное ФИО, birth_date).
Используется из шаблона как `do_info(child)` через context_processor.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

_CACHE: dict[str, Any] = {"data": None, "mtime": 0.0, "path": None}
_LOCK = threading.Lock()


def _candidate_paths() -> list[str]:
    env = os.getenv("DO_INDEX_PATH")
    here = os.path.dirname(os.path.abspath(__file__))
    rels = [
        "../data/do_index.json",
        "data/do_index.json",
        "../../data/do_index.json",
        "../do_2526/do_index.json",
        "../../do_2526/do_index.json",
    ]
    paths = [env] if env else []
    paths.extend(os.path.normpath(os.path.join(here, r)) for r in rels)
    return [p for p in paths if p]


def _json_path() -> str | None:
    for p in _candidate_paths():
        if os.path.isfile(p):
            return p
    return None


def _normalize(s: Any) -> str:
    if not s:
        return ""
    return str(s).strip().lower().replace("ё", "е")


def _build_index(raw: dict) -> dict:
    students = raw.get("students") or []
    by_key: dict[tuple, list] = {}
    for s in students:
        key = (
            _normalize(s.get("last")),
            _normalize(s.get("first")),
            _normalize(s.get("middle")),
            (s.get("birth_date") or "")[:10],
        )
        by_key[key] = s.get("programs") or []
    return {
        "by_key": by_key,
        "valid_from": raw.get("valid_from") or "",
        "valid_to": raw.get("valid_to") or "",
        "source": raw.get("source") or "",
    }


def _load_index() -> dict | None:
    path = _json_path()
    if not path:
        return None
    mtime = os.path.getmtime(path)
    with _LOCK:
        if _CACHE["data"] and _CACHE["mtime"] == mtime and _CACHE["path"] == path:
            return _CACHE["data"]
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        _CACHE["data"] = _build_index(raw)
        _CACHE["mtime"] = mtime
        _CACHE["path"] = path
    return _CACHE["data"]


def _lookup_programs(idx: dict, child) -> list | None:
    bd = child.birth_date.isoformat() if getattr(child, "birth_date", None) else ""
    if not bd:
        return None
    key = (
        _normalize(getattr(child, "last_name", "")),
        _normalize(getattr(child, "first_name", "")),
        _normalize(getattr(child, "middle_name", "")),
        bd,
    )
    return idx["by_key"].get(key)


def is_in_do(child) -> bool:
    if child is None:
        return False
    idx = _load_index()
    if not idx:
        return False
    progs = _lookup_programs(idx, child)
    return bool(progs)


def count_in_do_for_children(children) -> int:
    if not children:
        return 0
    idx = _load_index()
    if not idx:
        return 0
    cnt = 0
    for ch in children:
        if _lookup_programs(idx, ch):
            cnt += 1
    return cnt


def get_info_for_child(child) -> dict | None:
    """Возвращает {programs, count, valid_from, valid_to} если ребёнок есть в выгрузке.
    None — нет в выгрузке (или вообще нет источника данных)."""
    if child is None:
        return None
    idx = _load_index()
    if not idx:
        return None
    progs = _lookup_programs(idx, child)
    if not progs:
        return None
    programs_sorted = sorted(progs, key=lambda p: (p.get("program") or "").lower())
    return {
        "in_do": True,
        "programs": programs_sorted,
        "count": len(programs_sorted),
        "valid_from": idx.get("valid_from"),
        "valid_to": idx.get("valid_to"),
    }


import re as _re

_RE_YEAR = _re.compile(r"\s*\d{2}\s*/\s*\d{2}.*$")
_RE_GROUP = _re.compile(r"\s*группа\s*\d+\s*$", _re.IGNORECASE)
_RE_CLASS_LETTERED = _re.compile(r"\s+(\d{1,2})\s*[-–]?\s*[А-ЯЁA-Z]{1,4}\s*$")
_RE_PARALLEL_TAIL = _re.compile(r"\s+(\d{1,2})\s*$")


def _canonicalize_program(raw: str) -> tuple[str, int | None]:
    """Сводит сырое название программы к (base, parallel).

    Срезает: год '25/26 ...', хвост 'группа NN', буквенный класс ('7ФГ', '8 АН',
    '9-БШ'), либо просто параллель в конце ('Хор 5'). Параллель возвращается
    отдельным числом, чтобы группировать «по названию и возрасту».
    """
    s = (raw or "").strip().strip('"').strip("«»").strip()
    s = _RE_YEAR.sub("", s).strip()
    s = _RE_GROUP.sub("", s).strip()
    parallel: int | None = None
    m = _RE_CLASS_LETTERED.search(s)
    if m:
        try:
            parallel = int(m.group(1))
        except ValueError:
            pass
        s = _RE_CLASS_LETTERED.sub("", s).strip()
    else:
        m = _RE_PARALLEL_TAIL.search(s)
        if m:
            try:
                parallel = int(m.group(1))
            except ValueError:
                pass
            s = _RE_PARALLEL_TAIL.sub("", s).strip()
    s = s.strip(' "«»').strip()
    return s, parallel


def _canonical_label(raw: str) -> str:
    base, parallel = _canonicalize_program(raw)
    if not base:
        return raw or ""
    if parallel is None:
        return base
    return f"{base} ({parallel} класс)"


def _canonical_key(raw: str) -> str:
    base, parallel = _canonicalize_program(raw)
    return f"{base.casefold().replace('ё', 'е')}|{parallel if parallel is not None else ''}"


def list_programs() -> list[str]:
    """Уникальные канонические названия программ ('База (N класс)'), отсортированы."""
    idx = _load_index()
    if not idx:
        return []
    by_key: dict[str, str] = {}
    for progs in idx["by_key"].values():
        for p in progs or []:
            raw = (p.get("program") or "").strip()
            if not raw:
                continue
            k = _canonical_key(raw)
            if k not in by_key:
                by_key[k] = _canonical_label(raw)
    return sorted(by_key.values(), key=lambda s: s.casefold())


def count_in_program_for_children(children, program_name: str) -> int:
    """Сколько из переданных Child записаны на программу.
    Сравнение по канонизированному ключу (объединяет «X 7ФГ», «X 7БШ» и т.д.).
    Принимает как канонический лейбл из dropdown, так и любой свободный ввод.
    """
    if not children or not program_name:
        return 0
    idx = _load_index()
    if not idx:
        return 0
    target_key = _canonical_key(program_name)
    if not target_key.split("|")[0]:
        return 0
    cnt = 0
    for ch in children:
        progs = _lookup_programs(idx, ch) or []
        for p in progs:
            if _canonical_key(p.get("program") or "") == target_key:
                cnt += 1
                break
    return cnt


def get_meta() -> dict:
    """Возвращает {valid_from, valid_to} даже если у ребёнка нет записей."""
    idx = _load_index()
    if not idx:
        return {"valid_from": "", "valid_to": ""}
    return {
        "valid_from": idx.get("valid_from") or "",
        "valid_to": idx.get("valid_to") or "",
    }
