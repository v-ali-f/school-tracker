import os
import json
import mimetypes
from datetime import datetime
from typing import Iterable, Optional

import requests
from flask import Blueprint, current_app, jsonify, request, abort
from flask_login import login_required, current_user

from . import db
from .models import User, Document, MaxDeliveryLog, FamiliarizationAck
from .roles import require_roles
from .documents import _abs_path

max_bot_bp = Blueprint("max_bot", __name__, url_prefix="/max")


class MaxBotError(RuntimeError):
    pass


def _token() -> str:
    return (os.getenv("MAX_BOT_TOKEN") or current_app.config.get("MAX_BOT_TOKEN") or "").strip()


def _api_base() -> str:
    return (os.getenv("MAX_API_BASE") or "https://platform-api.max.ru").rstrip("/")


def _headers() -> dict:
    token = _token()
    if not token:
        raise MaxBotError("Не задан MAX_BOT_TOKEN")
    return {"Authorization": token}


def _max_enabled() -> bool:
    return bool(_token())


def _recipient_id(user: User) -> Optional[str]:
    return (getattr(user, "max_user_id", None) or getattr(user, "max_chat_id", None) or "").strip() or None


def upload_file_to_max(file_path: str, file_name: Optional[str] = None) -> str:
    """Загружает файл в MAX и возвращает token вложения.

    Основной сценарий MAX: POST /uploads?type=file -> загрузка по полученному URL -> token используется
    в POST /messages как attachment. Метод оставлен изолированным, чтобы при изменении API поправить одно место.
    """
    if not os.path.isfile(file_path):
        raise MaxBotError(f"Файл не найден: {file_path}")

    file_name = file_name or os.path.basename(file_path)
    mime = mimetypes.guess_type(file_name)[0] or "application/octet-stream"

    init_resp = requests.post(
        f"{_api_base()}/uploads",
        params={"type": "file"},
        headers=_headers(),
        timeout=30,
    )
    if init_resp.status_code >= 400:
        raise MaxBotError(f"MAX upload init error: {init_resp.status_code} {init_resp.text}")

    init_data = init_resp.json() if init_resp.content else {}
    upload_url = init_data.get("url") or init_data.get("upload_url")
    token = init_data.get("token")
    if not upload_url:
        raise MaxBotError(f"MAX не вернул URL загрузки: {init_data}")

    with open(file_path, "rb") as f:
        upload_resp = requests.post(
            upload_url,
            files={"data": (file_name, f, mime)},
            timeout=180,
        )
    if upload_resp.status_code >= 400:
        raise MaxBotError(f"MAX upload file error: {upload_resp.status_code} {upload_resp.text}")

    if not token:
        try:
            upload_data = upload_resp.json() if upload_resp.content else {}
        except Exception:
            upload_data = {}
        token = upload_data.get("token") or upload_data.get("retval", {}).get("token")

    if not token:
        raise MaxBotError("MAX не вернул token загруженного файла")
    return token


def send_max_message(
    recipient_id: str,
    text: str,
    attachment_tokens: Optional[Iterable[str]] = None,
    buttons: Optional[list] = None,
) -> dict:
    attachments = []
    for token in attachment_tokens or []:
        attachments.append({"type": "file", "payload": {"token": token}})

    if buttons:
        attachments.append({"type": "inline_keyboard", "payload": {"buttons": buttons}})

    payload = {"recipient": {"user_id": recipient_id}, "text": text}
    if attachments:
        payload["attachments"] = attachments

    resp = requests.post(
        f"{_api_base()}/messages",
        headers={**_headers(), "Content-Type": "application/json"},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=30,
    )
    if resp.status_code >= 400:
        raise MaxBotError(f"MAX send message error: {resp.status_code} {resp.text}")
    return resp.json() if resp.content else {}


def send_document_for_familiarization(doc: Document, user: User, portal_url: Optional[str] = None) -> MaxDeliveryLog:
    recipient = _recipient_id(user)
    if not recipient:
        raise MaxBotError(f"У пользователя {user.fio or user.username} не задан max_user_id/max_chat_id")

    path = _abs_path(doc.stored_path)
    token = upload_file_to_max(path, doc.original_name)

    text = (
        "Вам направлен документ для ознакомления.\n\n"
        f"Документ: {doc.title or doc.original_name}\n"
        "Файл прикреплён к сообщению. После ознакомления нажмите кнопку ниже."
    )
    buttons = [[
        {"type": "callback", "text": "Ознакомлен", "payload": f"ack_document:{doc.id}:{user.id}"}
    ]]
    if portal_url:
        buttons.append([{"type": "link", "text": "Открыть в портале", "url": portal_url}])

    result = send_max_message(recipient, text, [token], buttons)
    log = MaxDeliveryLog(
        module="familiarization",
        entity_type="document",
        entity_id=doc.id,
        user_id=user.id,
        max_recipient_id=recipient,
        max_message_id=str(result.get("message_id") or result.get("id") or ""),
        file_token=token,
        file_original_name=doc.original_name,
        status="sent",
        sent_at=datetime.utcnow(),
    )
    db.session.add(log)
    db.session.commit()
    return log


def send_task_to_max_with_files(
    *,
    task_id: int,
    task_title: str,
    task_text: str,
    recipient_user: User,
    attachment_paths: Iterable[str],
    portal_url: Optional[str] = None,
) -> MaxDeliveryLog:
    """Единая функция для задач/поручений.

    В актуальном tasks.py после создания задачи/поручения нужно передать сюда список файлов,
    которые уже лежат на сервере портала.
    """
    recipient = _recipient_id(recipient_user)
    if not recipient:
        raise MaxBotError(f"У пользователя {recipient_user.fio or recipient_user.username} не задан max_user_id/max_chat_id")

    tokens = [upload_file_to_max(p, os.path.basename(p)) for p in attachment_paths if p and os.path.isfile(p)]
    text = f"Новое поручение/задача:\n\n{task_title}\n\n{task_text or ''}"
    buttons = []
    if portal_url:
        buttons.append([{"type": "link", "text": "Открыть задачу в портале", "url": portal_url}])

    result = send_max_message(recipient, text, tokens, buttons or None)
    log = MaxDeliveryLog(
        module="tasks",
        entity_type="task",
        entity_id=task_id,
        user_id=recipient_user.id,
        max_recipient_id=recipient,
        max_message_id=str(result.get("message_id") or result.get("id") or ""),
        file_original_name=", ".join(os.path.basename(p) for p in attachment_paths if p),
        status="sent",
        sent_at=datetime.utcnow(),
    )
    db.session.add(log)
    db.session.commit()
    return log


@max_bot_bp.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    callback = data.get("callback") or data.get("callback_query") or data.get("update", {}).get("callback") or {}
    payload = callback.get("payload") or data.get("payload") or ""
    callback_id = callback.get("callback_id") or data.get("callback_id")

    if payload.startswith("ack_document:"):
        _, doc_id_raw, user_id_raw = payload.split(":", 2)
        doc_id = int(doc_id_raw)
        user_id = int(user_id_raw)
        ack = FamiliarizationAck.query.filter_by(document_id=doc_id, user_id=user_id).first()
        if not ack:
            ack = FamiliarizationAck(document_id=doc_id, user_id=user_id)
            db.session.add(ack)
        ack.acknowledged_at = datetime.utcnow()
        ack.source = "max_bot"
        ack.max_callback_id = str(callback_id or "")
        db.session.commit()

        if callback_id:
            try:
                requests.post(
                    f"{_api_base()}/answers",
                    headers={**_headers(), "Content-Type": "application/json"},
                    json={"callback_id": callback_id, "text": "Ознакомление зафиксировано"},
                    timeout=15,
                )
            except Exception:
                pass
        return jsonify({"ok": True, "status": "acknowledged"})

    return jsonify({"ok": True, "status": "ignored"})


@max_bot_bp.route("/documents/<int:doc_id>/send/<int:user_id>", methods=["POST"])
@login_required
@require_roles("ADMIN")
def send_document_route(doc_id: int, user_id: int):
    if not _max_enabled():
        abort(400, "Не задан MAX_BOT_TOKEN")
    doc = Document.query.get_or_404(doc_id)
    user = User.query.get_or_404(user_id)
    portal_url = request.form.get("portal_url")
    log = send_document_for_familiarization(doc, user, portal_url=portal_url)
    return jsonify({"ok": True, "delivery_id": log.id})
