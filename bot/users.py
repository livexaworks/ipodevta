"""Drain Telegram getUpdates and apply /start + customize commands."""

from __future__ import annotations

import logging
from typing import Any

import requests

from bot import config, notify, state

log = logging.getLogger(__name__)

OFFSET_PATH = config.DATA_DIR / "telegram_offset.json"

HELP = (
    "IPO Devta — personalized IPO screening.\n"
    "Information only, not investment advice.\n\n"
    "How it works\n"
    "• Weekday mornings: if IPOs close that day, you get a DM "
    "scored with YOUR prefs (👍/👎 + numbers).\n"
    "• Public channel: unfiltered GMP feed for the same day.\n"
    "• Grey-market premium is unofficial and can be manipulated. Read the RHP.\n\n"
    "Commands (tap / or type them)\n"
    "/start — register + show this guide\n"
    "/help — show this guide again\n"
    "/settings — show your current prefs\n"
    "/status — same as /settings\n"
    "/gmp 30 — set min GMP % (example: 30)\n"
    "/sub 2 — set min total subscription in times (example: 2x)\n"
    "/board main — MAIN board only\n"
    "/board all — MAIN + SME\n\n"
    "Replies usually arrive within about an hour on weekdays "
    "(free GitHub Actions — not an always-on server). "
    "After you send a command, wait for the confirmation DM before changing it again."
)

BOT_COMMANDS = [
    {"command": "start", "description": "Register and show the guide"},
    {"command": "help", "description": "Show commands and how alerts work"},
    {"command": "settings", "description": "Show your current prefs"},
    {"command": "status", "description": "Same as /settings"},
    {"command": "gmp", "description": "Set min GMP %, e.g. /gmp 30"},
    {"command": "sub", "description": "Set min total sub, e.g. /sub 2"},
    {"command": "board", "description": "MAIN only or MAIN+SME: /board main|all"},
]


def _load_offset() -> int | None:
    if not OFFSET_PATH.is_file():
        return None
    try:
        import json

        data = json.loads(OFFSET_PATH.read_text(encoding="utf-8"))
        return int(data.get("offset")) if data.get("offset") is not None else None
    except Exception:  # noqa: BLE001
        return None


def _save_offset(offset: int) -> None:
    import json

    OFFSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_PATH.write_text(json.dumps({"offset": offset}) + "\n", encoding="utf-8")


def _api(method: str, **params: Any) -> dict[str, Any]:
    token = config.telegram_token()
    if not token:
        raise notify.NotifyError("TELEGRAM_TOKEN is not set")
    url = f"https://api.telegram.org/bot{token}/{method}"
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()
    if not data.get("ok"):
        raise notify.NotifyError(f"Telegram {method} failed: {data}")
    return data


def ensure_bot_commands() -> None:
    """Register the / menu so users see every command in Telegram."""
    token = config.telegram_token()
    if not token:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/setMyCommands"
        resp = requests.post(url, json={"commands": BOT_COMMANDS}, timeout=30)
        data = resp.json()
        if not data.get("ok"):
            log.warning("setMyCommands failed: %s", data)
    except Exception as exc:  # noqa: BLE001
        log.warning("setMyCommands failed: %s", exc)


def _prefs_text(prefs: dict[str, Any]) -> str:
    board = "MAIN + SME" if prefs.get("include_sme") else "MAIN only"
    return (
        f"Your prefs:\n"
        f"  min GMP %: {prefs.get('min_gmp_pct')}\n"
        f"  min total sub: {prefs.get('min_total_sub')}x\n"
        f"  board: {board}\n"
        f"Updated: {prefs.get('updated', 'n/a')}"
    )


def handle_text(chat_id: int | str, text: str, *, dry_run: bool) -> None:
    raw = (text or "").strip()
    if not raw:
        return
    parts = raw.split()
    cmd = parts[0].lower().split("@")[0]

    if cmd in ("/start", "start", "/help", "help"):
        prefs = state.get_or_create_user(chat_id)
        msg = f"Registered.\n\n{_prefs_text(prefs)}\n\n{HELP}"
        notify.send_message(chat_id, msg, parse_mode=None, dry_run=dry_run)
        return

    if cmd in ("/settings", "/status", "settings", "status"):
        prefs = state.get_or_create_user(chat_id)
        notify.send_message(
            chat_id,
            f"{_prefs_text(prefs)}\n\nTip: /help for the full command list.",
            parse_mode=None,
            dry_run=dry_run,
        )
        return

    if cmd in ("/gmp", "gmp"):
        if len(parts) < 2:
            notify.send_message(chat_id, "Usage: /gmp 30", parse_mode=None, dry_run=dry_run)
            return
        try:
            val = float(parts[1])
        except ValueError:
            notify.send_message(chat_id, "GMP must be a number", parse_mode=None, dry_run=dry_run)
            return
        prefs = state.update_user(chat_id, min_gmp_pct=val)
        notify.send_message(
            chat_id,
            f"Saved.\n\n{_prefs_text(prefs)}",
            parse_mode=None,
            dry_run=dry_run,
        )
        return

    if cmd in ("/sub", "sub"):
        if len(parts) < 2:
            notify.send_message(chat_id, "Usage: /sub 2", parse_mode=None, dry_run=dry_run)
            return
        try:
            val = float(parts[1])
        except ValueError:
            notify.send_message(chat_id, "Sub must be a number", parse_mode=None, dry_run=dry_run)
            return
        prefs = state.update_user(chat_id, min_total_sub=val)
        notify.send_message(
            chat_id,
            f"Saved.\n\n{_prefs_text(prefs)}",
            parse_mode=None,
            dry_run=dry_run,
        )
        return

    if cmd in ("/board", "board"):
        if len(parts) < 2 or parts[1].lower() not in ("main", "all", "sme"):
            notify.send_message(
                chat_id, "Usage: /board main | /board all", parse_mode=None, dry_run=dry_run
            )
            return
        include = parts[1].lower() in ("all", "sme")
        prefs = state.update_user(chat_id, include_sme=include)
        notify.send_message(
            chat_id,
            f"Saved.\n\n{_prefs_text(prefs)}",
            parse_mode=None,
            dry_run=dry_run,
        )
        return

    if cmd.startswith("/"):
        notify.send_message(chat_id, HELP, parse_mode=None, dry_run=dry_run)
        return

    # Plain text — nudge toward the menu
    notify.send_message(
        chat_id,
        "I only understand slash commands.\nTap / or send /help for the guide.",
        parse_mode=None,
        dry_run=dry_run,
    )


def drain_updates(*, dry_run: bool = False) -> int:
    """Process queued Telegram updates. Returns number handled."""
    if not config.telegram_token():
        log.warning("TELEGRAM_TOKEN unset — skip getUpdates")
        return 0

    ensure_bot_commands()

    offset = _load_offset()
    params: dict[str, Any] = {"timeout": 0, "allowed_updates": '["message"]'}
    if offset is not None:
        params["offset"] = offset

    try:
        data = _api("getUpdates", **params)
    except Exception as exc:  # noqa: BLE001
        log.error("getUpdates failed: %s", exc)
        return 0

    results = data.get("result") or []
    handled = 0
    max_update = offset
    for upd in results:
        uid = upd.get("update_id")
        if uid is not None:
            max_update = uid + 1 if max_update is None else max(max_update, uid + 1)
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        text = msg.get("text") or ""
        if chat_id is None:
            continue
        try:
            handle_text(chat_id, text, dry_run=dry_run)
            handled += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed handling update from %s: %s", chat_id, exc)

    if max_update is not None and not dry_run:
        _save_offset(max_update)
    return handled
