"""Школьный спортивный клуб: матчинг учеников с выгрузкой schoolsportmos.

Источник — JSON-выгрузка `sportmos/full.json`:
  pupils         — список учеников с meshID и ФИО/birthday
  teamPlayers    — состав команд (playerID → teamID)
  teams          — справочник команд
  requests       — заявки школы на мероприятия (event_title, stage, final_place)

Матчинг с нашим Child делается по паре (ФИО, birth_date). meshID в Child пока не хранится,
поэтому fallback по ФИО+birthday — основной путь.

Используется из шаблона как `sport_club_info(child)` — см. context_processors.py.
"""
from __future__ import annotations

import json
import os
import threading
from collections import Counter, defaultdict
from typing import Any


SPORT_TYPE_LABELS = {
    1: "Баскетбол",
    2: "Бадминтон",
    3: "Волейбол",
    4: "Футбол",
    6: "Гандбол",
    7: "Настольный теннис",
    9: "Плавание",
    12: "Лёгкая атлетика",
    19: "Мини-футбол",
    20: "Президентские состязания",
    21: "Президентские спортивные игры",
    22: "Регби",
    23: "ГТО",
    26: "Шашки",
    29: "Лапта",
}

REQUEST_STATUS_LABELS = {
    1: "Принята",
    4: "Завершена",
}

_CACHE: dict[str, Any] = {"data": None, "mtime": 0.0, "path": None}
_LOCK = threading.Lock()


def _candidate_paths() -> list[str]:
    env = os.getenv("SPORTMOS_JSON_PATH")
    here = os.path.dirname(os.path.abspath(__file__))
    rels = [
        "../../sportmos/full.json",
        "../sportmos/full.json",
        "../data/sportmos/full.json",
        "data/sportmos/full.json",
        "../../data/sportmos/full.json",
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
    pupils = raw.get("pupils") or []
    teams = raw.get("teams") or []
    team_players = raw.get("teamPlayers") or []
    requests_list = raw.get("requests") or []

    pupils_by_id: dict[int, dict] = {}
    by_mesh: dict[str, int] = {}
    by_fio_bday: dict[tuple, int] = {}

    for p in pupils:
        pid = p.get("ID")
        if pid is None:
            continue
        pupils_by_id[pid] = p
        mesh = (p.get("meshID") or "").strip()
        if mesh and mesh != "0":
            by_mesh[mesh] = pid
        key = (
            _normalize(p.get("f")),
            _normalize(p.get("i")),
            _normalize(p.get("o")),
            p.get("birthday") or "",
        )
        by_fio_bday[key] = pid

    teams_by_id = {t["ID"]: t for t in teams if "ID" in t}

    teams_per_pupil: dict[int, list[dict]] = defaultdict(list)
    for tp in team_players:
        try:
            pid = int(tp.get("playerID"))
        except (TypeError, ValueError):
            continue
        team_id = tp.get("teamID")
        team = teams_by_id.get(team_id, {})
        teams_per_pupil[pid].append(
            {
                "team_id": team_id,
                "team_title": (tp.get("team_title") or team.get("title") or "").strip(),
                "sport_type": team.get("sport_type"),
                "archive": bool(team.get("archive")),
                "joined_at": tp.get("create_time"),
            }
        )

    reqs_by_team: dict[int, list[dict]] = defaultdict(list)
    for r in requests_list:
        reqs_by_team[r.get("teamID")].append(
            {
                "event_title": (r.get("event_title") or "").strip(),
                "stage_title": (r.get("stage_title") or "").strip(),
                "status": r.get("status"),
                "final_place": r.get("final_place"),
                "created_at": r.get("create_time"),
            }
        )

    return {
        "pupils_by_id": pupils_by_id,
        "by_mesh": by_mesh,
        "by_fio_bday": by_fio_bday,
        "teams_per_pupil": teams_per_pupil,
        "reqs_by_team": reqs_by_team,
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


def _primary_sport_label(teams: list[dict]) -> str | None:
    labels = [
        SPORT_TYPE_LABELS.get(t.get("sport_type"))
        for t in teams
        if t.get("sport_type") is not None
    ]
    labels = [l for l in labels if l]
    if not labels:
        return None
    return Counter(labels).most_common(1)[0][0]


def _lookup_pupil_id(idx: dict, child) -> int | None:
    mesh = (getattr(child, "mesh_id", "") or "").strip()
    if mesh:
        pid = idx["by_mesh"].get(mesh)
        if pid is not None:
            return pid
    bd = child.birth_date.isoformat() if getattr(child, "birth_date", None) else ""
    if not bd:
        return None
    key = (
        _normalize(getattr(child, "last_name", "")),
        _normalize(getattr(child, "first_name", "")),
        _normalize(getattr(child, "middle_name", "")),
        bd,
    )
    return idx["by_fio_bday"].get(key)


def is_in_club(child) -> bool:
    """Быстрая проверка «состоит в ШСК». Используется в batch-подсчётах
    (список класса, реестры) — возвращает True только если нашли ребёнка
    в sportmos-выгрузке и у него есть хотя бы одна команда (active или архив)."""
    if child is None:
        return False
    idx = _load_index()
    if not idx:
        return False
    pid = _lookup_pupil_id(idx, child)
    if pid is None:
        return False
    return bool(idx["teams_per_pupil"].get(pid))


def count_in_club_for_children(children) -> int:
    """Сколько из переданных Child состоят в ШСК. Один load_index, без I/O.
    Пустой список/None → 0."""
    if not children:
        return 0
    idx = _load_index()
    if not idx:
        return 0
    cnt = 0
    for ch in children:
        pid = _lookup_pupil_id(idx, ch)
        if pid is not None and idx["teams_per_pupil"].get(pid):
            cnt += 1
    return cnt


def get_info_for_child(child) -> dict | None:
    """Возвращает сведения о ребёнке из sportmos, если он есть в выгрузке И состоит хотя бы в одной команде.
    None означает «не в клубе» — плашку с раскрытием рисовать не нужно
    (но шаблон может показать короткую строку «не состоит»).
    """
    if child is None:
        return None
    idx = _load_index()
    if not idx:
        return None
    pid = _lookup_pupil_id(idx, child)
    if pid is None:
        return None
    teams = list(idx["teams_per_pupil"].get(pid, []))
    if not teams:
        return None

    active_teams = [t for t in teams if not t.get("archive")]
    active_sorted = sorted(active_teams, key=lambda t: t.get("joined_at") or "", reverse=True)
    archived_sorted = sorted([t for t in teams if t.get("archive")], key=lambda t: t.get("joined_at") or "", reverse=True)
    teams_sorted = active_sorted + archived_sorted

    events: list[dict] = []
    seen: set[tuple] = set()
    for t in teams:
        for e in idx["reqs_by_team"].get(t.get("team_id"), []):
            key = (e.get("event_title"), e.get("stage_title"), t.get("team_id"))
            if key in seen:
                continue
            seen.add(key)
            events.append(
                {
                    **e,
                    "team_title": t.get("team_title"),
                    "sport_type": t.get("sport_type"),
                    "sport_label": SPORT_TYPE_LABELS.get(t.get("sport_type")),
                    "status_label": REQUEST_STATUS_LABELS.get(e.get("status")),
                }
            )
    events.sort(key=lambda e: e.get("created_at") or "", reverse=True)

    pupil = idx["pupils_by_id"].get(pid, {})
    for t in teams_sorted:
        t["sport_label"] = SPORT_TYPE_LABELS.get(t.get("sport_type"))

    sport_labels_unique: list[str] = []
    for t in teams_sorted:
        lbl = SPORT_TYPE_LABELS.get(t.get("sport_type"))
        if lbl and lbl not in sport_labels_unique:
            sport_labels_unique.append(lbl)

    return {
        "in_club": True,
        "pupil_id": pid,
        "teams": teams_sorted,
        "active_teams_count": len(active_teams),
        "events": events,
        "primary_sport": _primary_sport_label(teams),
        "sports": sport_labels_unique,
        "photo_count": pupil.get("photo_count") or 0,
    }
