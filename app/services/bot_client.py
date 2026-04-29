"""HTTP-клиент к MAX-боту (POLLING-архитектура).

Бот живёт на Amvera, портал во внутренней сети ходит к нему исходящими
HTTPS. Все запросы подписаны HMAC-SHA256:
    X-Bot-Timestamp: unix-время
    X-Bot-Signature: hmac_sha256(secret, f"{ts}:" + body)
Сам секрет по сети не передаётся — подпись гарантирует, что отправитель
знает секрет, без раскрытия в заголовках.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import os
import time

import requests


class BotClient:
    def __init__(self, base_url: str | None = None, secret: str | None = None, timeout: int = 10):
        self.base_url = (base_url or os.environ.get("BOT_API_URL", "")).rstrip("/")
        self.secret = (secret or os.environ.get("BOT_SHARED_SECRET", "")).encode()
        self.timeout = timeout

    def _enabled(self) -> bool:
        return bool(self.base_url) and bool(self.secret)

    def _headers(self, body: bytes):
        ts = str(int(time.time()))
        sig = hmac.new(self.secret, (ts + ":").encode() + body, hashlib.sha256).hexdigest()
        return {
            "X-Bot-Timestamp": ts,
            "X-Bot-Signature": sig,
            "Content-Type": "application/json",
        }

    def _get(self, path: str):
        body = b""
        r = requests.get(self.base_url + path, headers=self._headers(body), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        r = requests.post(self.base_url + path, data=body, headers=self._headers(body), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _get_binary(self, path: str, timeout: int = 60):
        body = b""
        r = requests.get(self.base_url + path, headers=self._headers(body), timeout=timeout)
        r.raise_for_status()
        return r.content, r.headers.get("Content-Type", "application/octet-stream")

    # --- API бота ---
    def pending(self):
        return self._get("/api/pending").get("items", [])

    def ack(self, queue_id: str, ok: bool, incident_id=None, link=None, error=None):
        return self._post("/api/ack", {
            "queue_id": queue_id, "ok": ok,
            "incident_id": incident_id, "incident_link": link, "error": error,
        })

    def pending_binds(self):
        return self._get("/api/pending_binds").get("items", [])

    def bind_result(self, *, chat_id, code, ok, user_id=None, full_name=None, role=None,
                    class_ids_meta=None, students=None):
        return self._post("/api/bind_result", {
            "chat_id": chat_id, "code": code, "ok": ok,
            "user_id": user_id, "full_name": full_name, "role": role,
            "class_ids_meta": class_ids_meta or [], "students": students or [],
        })

    def revoke(self, *, chat_id):
        return self._post("/api/revoke", {"chat_id": chat_id})

    def fetch_attachment(self, queue_id: str, idx: int):
        """Скачивает байты вложения с бота. Возвращает (bytes, content_type)."""
        return self._get_binary(f"/api/attachment/{queue_id}/{int(idx)}", timeout=120)


def get_client() -> BotClient:
    return BotClient()
