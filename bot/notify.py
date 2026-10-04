"""Telegram send helpers: channel broadcast, user DM, admin alerts."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from bot import config

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"

# ~20 messages/sec
_MIN_INTERVAL_SEC = 0.05
_last_send_monotonic = 0.0


class NotifyError(RuntimeError):
    pass


def _throttle() -> None:
    global _last_send_monotonic
    now = time.monotonic()
    wait = _MIN_INTERVAL_SEC - (now - _last_send_monotonic)
    if wait > 0:
        time.sleep(wait)
    _last_send_monotonic = time.monotonic()


def _post(
    method: str,
    payload: dict[str, Any],
    *,
    dry_run: bool = False,
    _retries: int = 3,
) -> dict[str, Any]:
    token = config.telegram_token()
    if not token:
        raise NotifyError("TELEGRAM_TOKEN is not set")
    if dry_run:
        log.info("dry-run skip Telegram %s -> chat_id=%s", method, payload.get("chat_id"))
        return {"ok": True, "dry_run": True}

    url = API.format(token=token, method=method)
    for attempt in range(_retries):
        _throttle()
        resp = requests.post(url, json=payload, timeout=30)
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise NotifyError(f"Telegram {method}: non-JSON ({resp.status_code})") from exc

        if data.get("ok"):
            return data

        # Honor 429 retry_after
        err_code = data.get("error_code")
        if err_code == 429 or resp.status_code == 429:
            params = data.get("parameters") or {}
            retry_after = params.get("retry_after", 1)
            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = 1.0
            log.warning("Telegram 429 on %s; sleeping %.1fs", method, delay)
            time.sleep(max(0.1, delay))
            continue

        raise NotifyError(f"Telegram {method} failed: {data}")

    raise NotifyError(f"Telegram {method} failed after {_retries} retries: 429")


def send_message(
    chat_id: str | int,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: dict[str, Any] | None = None,
    disable_notification: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "link_preview_options": {"is_disabled": True},
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if disable_notification:
        payload["disable_notification"] = True
    return _post("sendMessage", payload, dry_run=dry_run)


def edit_message(
    chat_id: str | int,
    message_id: int,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "link_preview_options": {"is_disabled": True},
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return _post("editMessageText", payload, dry_run=dry_run)


def answer_callback(
    callback_query_id: str,
    *,
    text: str | None = None,
    show_alert: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    return _post("answerCallbackQuery", payload, dry_run=dry_run)


def broadcast(
    html: str,
    *,
    disable_notification: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Post to the public channel (generic unfiltered feed)."""
    return send_message(
        config.channel_id(),
        html,
        disable_notification=disable_notification,
        dry_run=dry_run,
    )


def dm(
    chat_id: str | int,
    html: str,
    *,
    reply_markup: dict[str, Any] | None = None,
    disable_notification: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Personalized message to one user."""
    return send_message(
        chat_id,
        html,
        reply_markup=reply_markup,
        disable_notification=disable_notification,
        dry_run=dry_run,
    )


def admin(text: str, *, dry_run: bool = False) -> dict[str, Any] | None:
    """Failure / ops alert to admin private chat. Plain text (no HTML)."""
    chat = config.admin_chat_id()
    if not chat:
        log.warning("ADMIN_CHAT_ID unset; admin message dropped: %s", text[:200])
        return None
    return send_message(chat, text, parse_mode=None, dry_run=dry_run)
