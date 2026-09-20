"""Telegram send helpers: channel broadcast, user DM, admin alerts."""

from __future__ import annotations

import logging
from typing import Any

import requests

from bot import config

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"


class NotifyError(RuntimeError):
    pass


def _post(method: str, payload: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    token = config.telegram_token()
    if not token:
        raise NotifyError("TELEGRAM_TOKEN is not set")
    if dry_run:
        log.info("dry-run skip Telegram %s -> chat_id=%s", method, payload.get("chat_id"))
        return {"ok": True, "dry_run": True}
    url = API.format(token=token, method=method)
    resp = requests.post(url, json=payload, timeout=30)
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise NotifyError(f"Telegram {method}: non-JSON ({resp.status_code})") from exc
    if not data.get("ok"):
        raise NotifyError(f"Telegram {method} failed: {data}")
    return data


def send_message(
    chat_id: str | int,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    dry_run: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _post("sendMessage", payload, dry_run=dry_run)


def broadcast(html: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Post to the public channel (generic unfiltered feed)."""
    return send_message(config.channel_id(), html, dry_run=dry_run)


def dm(chat_id: str | int, html: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Personalized message to one user."""
    return send_message(chat_id, html, dry_run=dry_run)


def admin(text: str, *, dry_run: bool = False) -> dict[str, Any] | None:
    """Failure / ops alert to admin private chat. Plain text (no HTML)."""
    chat = config.admin_chat_id()
    if not chat:
        log.warning("ADMIN_CHAT_ID unset; admin message dropped: %s", text[:200])
        return None
    return send_message(chat, text, parse_mode=None, dry_run=dry_run)
