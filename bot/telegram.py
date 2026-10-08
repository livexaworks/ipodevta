"""Telegram Bot API: paced sends, 429 retries, admin alerts."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from bot import config

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"

# Telegram allows ~20 msgs/min into one group/channel and ~1 msg/s into one private chat.
CHANNEL_INTERVAL_SEC = 3.2
PRIVATE_INTERVAL_SEC = 1.0
GLOBAL_INTERVAL_SEC = 0.05

_last_global = 0.0
_last_by_chat: dict[str, float] = {}


class TelegramError(RuntimeError):
    pass


class ChatUnavailable(TelegramError):
    """User blocked the bot or the chat no longer exists (HTTP 403 / 400 chat not found)."""


def _is_channel(chat_id: str | int) -> bool:
    s = str(chat_id)
    return s.startswith("@") or s.startswith("-")


def _pace(chat_id: str | int) -> None:
    global _last_global
    key = str(chat_id)
    interval = CHANNEL_INTERVAL_SEC if _is_channel(chat_id) else PRIVATE_INTERVAL_SEC
    now = time.monotonic()
    wait = max(
        GLOBAL_INTERVAL_SEC - (now - _last_global),
        interval - (now - _last_by_chat.get(key, -1e9)),
    )
    if wait > 0:
        time.sleep(wait)
    _last_global = _last_by_chat[key] = time.monotonic()


def call(method: str, payload: dict[str, Any], *, retries: int = 3) -> dict[str, Any]:
    token = config.telegram_token()
    if not token:
        raise TelegramError("TELEGRAM_TOKEN is not set")
    url = API.format(token=token, method=method)
    for _ in range(retries):
        if "chat_id" in payload:
            _pace(payload["chat_id"])
        resp = requests.post(url, json=payload, timeout=30)
        try:
            data = resp.json()
        except ValueError as exc:
            raise TelegramError(f"{method}: non-JSON response ({resp.status_code})") from exc
        if data.get("ok"):
            return data["result"]

        code = data.get("error_code") or resp.status_code
        desc = str(data.get("description") or "")
        if code == 429:
            delay = float((data.get("parameters") or {}).get("retry_after", 1))
            log.warning("Telegram 429 on %s; sleeping %.0fs", method, delay)
            time.sleep(max(1.0, delay))
            continue
        if code == 403 or "chat not found" in desc.lower():
            raise ChatUnavailable(f"{method}: {desc}")
        raise TelegramError(f"{method} failed: {code} {desc}")
    raise TelegramError(f"{method}: still rate limited after {retries} tries")


def send(
    chat_id: str | int,
    html: str,
    *,
    reply_markup: dict[str, Any] | None = None,
    silent: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": html,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if silent:
        payload["disable_notification"] = True
    return call("sendMessage", payload)


def admin(text: str) -> None:
    """Plain-text ops alert. Never raises."""
    chat = config.admin_chat_id()
    if not chat:
        log.warning("ADMIN_CHAT_ID unset; admin message dropped: %s", text[:200])
        return
    try:
        call("sendMessage", {"chat_id": chat, "text": text[:4000]})
    except Exception as exc:  # noqa: BLE001
        log.warning("admin alert failed: %s", exc)
