"""
Интеграция с Yandex DataLens — встраивание дашборда «Кубок школы»
в локальную систему инцидентов.

JWT подписывается PS256 приватным ключом встраивания, выданным
в DataLens. Payload по спецификации DataLens:
    embedId, dlEmbedService, iat, exp, params

Пример:
    https://datalens.yandex.cloud/embeds/dash#dl_embed_token=<JWT>
"""
from __future__ import annotations

import os
import time
from functools import lru_cache
from pathlib import Path

import jwt
from flask import Blueprint, abort, current_app, render_template, request
from flask_login import login_required

from .models import SchoolClass


datalens_bp = Blueprint("datalens", __name__)


def _project_root() -> Path:
    return Path(current_app.root_path).parent


@lru_cache(maxsize=1)
def _load_private_key() -> bytes | None:
    rel = os.getenv("DATALENS_PRIVATE_KEY_PATH", "instance/datalens_private_key.pem")
    path = _project_root() / rel
    if not path.exists():
        current_app.logger.warning("DataLens: private key not found at %s", path)
        return None
    return path.read_bytes()


def _embed_id_for(kind: str) -> str | None:
    mapping = {
        # Целый дашборд (выделенная страница /datalens/class/<id>)
        "dash": os.getenv("DATALENS_EMBED_ID_CLASS"),
        # Отдельный чарт «Класс-место-баллы» (компактно в карточке ученика/класса)
        "chart_class_score": os.getenv("DATALENS_EMBED_ID_CHART_CLASS_SCORE"),
    }
    return (mapping.get(kind) or "").strip() or None


def is_configured() -> bool:
    return bool(_load_private_key() and (_embed_id_for("dash") or _embed_id_for("chart_class_score")))


def _class_param_name() -> str:
    """Имя параметра класса в датасете DataLens.
    Пустое значение = не передавать фильтр (показываем дашборд целиком)."""
    return (os.getenv("DATALENS_CLASS_PARAM_NAME") or "").strip()


def _dash_base_url() -> str:
    return (os.getenv("DATALENS_EMBED_BASE_URL")
            or "https://datalens.yandex.cloud/embeds/dash").strip()


def _chart_base_url() -> str:
    # Для одиночных чартов DataLens использует /embeds/chart
    return (os.getenv("DATALENS_CHART_BASE_URL")
            or "https://datalens.yandex.cloud/embeds/chart").strip()


def dashboard_full_url() -> str:
    return (os.getenv("DATALENS_DASHBOARD_URL") or "").strip()


def build_embed_token(embed_id: str, params: dict, ttl_seconds: int = 300) -> str:
    key = _load_private_key()
    if not key:
        raise RuntimeError("DataLens private key is not configured")
    now = int(time.time())
    payload = {
        "embedId": embed_id,
        "dlEmbedService": "YC_DATALENS_EMBEDDING_SERVICE_MARK",
        "iat": now,
        "exp": now + ttl_seconds,
    }
    filtered = {k: str(v) for k, v in (params or {}).items() if v is not None}
    if filtered:
        payload["params"] = filtered
    return jwt.encode(payload=payload, key=key, algorithm="PS256")


def build_embed_url(base_url: str, embed_id: str, params: dict) -> str:
    token = build_embed_token(embed_id, params)
    return f"{base_url}#dl_embed_token={token}"


def class_embed_url(class_name: str | None) -> str | None:
    """URL для iframe дашборда кубка по классу."""
    embed_id = _embed_id_for("dash")
    if not embed_id or not _load_private_key():
        return None
    params = {}
    param_name = _class_param_name()
    if class_name and param_name:
        params[param_name] = class_name
    return build_embed_url(_dash_base_url(), embed_id, params)


def class_score_chart_url(class_name: str | None) -> str | None:
    """URL для iframe одиночного чарта «Класс-место-баллы»."""
    embed_id = _embed_id_for("chart_class_score")
    if not embed_id or not _load_private_key():
        return None
    params = {}
    param_name = _class_param_name()
    if class_name and param_name:
        params[param_name] = class_name
    return build_embed_url(_chart_base_url(), embed_id, params)


@datalens_bp.route("/datalens/class/<int:class_id>")
@login_required
def class_rating_page(class_id: int):
    from app.permissions import is_admin
    if not is_admin():
        abort(403)
    sc = SchoolClass.query.get_or_404(class_id)
    from app.kubok import get_rating, cache_status
    rating = get_rating(sc.name)
    return render_template(
        "datalens_class.html",
        school_class=sc,
        rating=rating,
        cache_status=cache_status(),
        full_dashboard_url=dashboard_full_url(),
    )


@datalens_bp.route("/datalens/class-embed-url")
@login_required
def class_embed_url_endpoint():
    """Отдельный endpoint для получения свежего URL (TTL токена короткий)."""
    class_name = (request.args.get("class_name") or "").strip()
    url = class_embed_url(class_name or None)
    if not url:
        abort(404)
    return {"url": url}
