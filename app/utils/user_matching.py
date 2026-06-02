import re
from typing import Optional, Tuple

from sqlalchemy import or_

from app.core.extensions import db
from app.models import User


def normalize_login(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def normalize_phone(value: Optional[str]) -> str:
    raw = re.sub(r"\D+", "", value or "")
    if raw.startswith("8") and len(raw) == 11:
        raw = "7" + raw[1:]
    return raw


def normalize_fio(last_name: Optional[str] = None, first_name: Optional[str] = None, middle_name: Optional[str] = None, fio: Optional[str] = None) -> str:
    if fio is None:
        fio = " ".join([x.strip() for x in [last_name or "", first_name or "", middle_name or ""] if (x or "").strip()])
    text = (fio or "").strip().lower().replace("ё", "е")
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_fio(fio: Optional[str]) -> Tuple[str, str, Optional[str]]:
    parts = [p for p in re.split(r"\s+", (fio or "").strip()) if p]
    if not parts:
        return "", "", None
    last_name = parts[0]
    first_name = parts[1] if len(parts) > 1 else ""
    middle_name = " ".join(parts[2:]) if len(parts) > 2 else None
    return last_name, first_name, middle_name


def find_existing_user(
    *,
    username: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    last_name: Optional[str] = None,
    first_name: Optional[str] = None,
    middle_name: Optional[str] = None,
    fio: Optional[str] = None,
):
    """Return (user, match_reason) or (None, reason).

    If more than one candidate is found for a strategy, returns (None, 'conflict:<kind>').
    """
    login_key = normalize_login(username)
    if login_key:
        items = User.query.filter(db.func.lower(User.username) == login_key).all()
        if len(items) == 1:
            return items[0], "username"
        if len(items) > 1:
            return None, "conflict:username"

    email_key = (email or "").strip().lower()
    if email_key:
        items = User.query.filter(db.func.lower(db.func.coalesce(User.email, "")) == email_key).all()
        if len(items) == 1:
            return items[0], "email"
        if len(items) > 1:
            return None, "conflict:email"

    phone_key = normalize_phone(phone)
    if phone_key:
        candidates = [u for u in User.query.filter(User.phone.isnot(None)).all() if normalize_phone(u.phone) == phone_key]
        if len(candidates) == 1:
            return candidates[0], "phone"
        if len(candidates) > 1:
            return None, "conflict:phone"

    full_fio = (fio or " ".join([x.strip() for x in [last_name or "", first_name or "", middle_name or ""] if (x or "").strip()])).strip()
    if full_fio:
        exact = User.query.filter(db.func.lower(db.func.trim(db.func.coalesce(User.last_name, "") + " " + db.func.coalesce(User.first_name, "") + " " + db.func.coalesce(User.middle_name, ""))) == full_fio.lower()).all()
        if len(exact) == 1:
            return exact[0], "fio"
        if len(exact) > 1:
            return None, "conflict:fio"

        fio_key = normalize_fio(fio=full_fio)
        candidates = [u for u in User.query.filter(or_(User.last_name.isnot(None), User.first_name.isnot(None))).all() if normalize_fio(u.last_name, u.first_name, u.middle_name) == fio_key]
        if len(candidates) == 1:
            return candidates[0], "normalized_fio"
        if len(candidates) > 1:
            return None, "conflict:normalized_fio"

    return None, "not_found"


def potential_duplicate_groups():
    users = User.query.order_by(User.last_name.asc(), User.first_name.asc(), User.username.asc()).all()
    groups = []

    by_norm_fio = {}
    for u in users:
        key = normalize_fio(u.last_name, u.first_name, u.middle_name)
        if key:
            by_norm_fio.setdefault(("normalized_fio", key), []).append(u)

    by_phone = {}
    for u in users:
        key = normalize_phone(u.phone)
        if key:
            by_phone.setdefault(("phone", key), []).append(u)

    by_email = {}
    for u in users:
        key = (u.email or "").strip().lower()
        if key:
            by_email.setdefault(("email", key), []).append(u)

    seen = set()
    for source in (by_norm_fio, by_phone, by_email):
        for (kind, key), items in source.items():
            if len(items) < 2:
                continue
            ids = tuple(sorted(u.id for u in items))
            if ids in seen:
                continue
            seen.add(ids)
            groups.append({
                "kind": kind,
                "key": key,
                "users": items,
            })

    groups.sort(key=lambda g: (-len(g["users"]), g["kind"], g["key"]))
    return groups
