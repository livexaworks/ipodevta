"""Drain Telegram updates — button-first UX with optional slash shortcuts."""

from __future__ import annotations

import logging
from typing import Any

import requests

from bot import config, keyboards, notify, preview, render, state

log = logging.getLogger(__name__)

OFFSET_PATH = config.DATA_DIR / "telegram_offset.json"

# Reply-keyboard labels (exact match)
BTN_PREVIEW = "Preview GMP"
BTN_SETTINGS = "Settings"
BTN_HELP = "Help"
BTN_CHANNEL = "Channel"

BOT_COMMANDS = [
    {"command": "start", "description": "Open IPO Devta"},
    {"command": "menu", "description": "Show main buttons"},
    {"command": "preview", "description": "Last 5 IPOs with your filters"},
    {"command": "settings", "description": "Adjust GMP / subscription / board"},
    {"command": "help", "description": "How the assistant works"},
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
    token = config.telegram_token()
    if not token:
        return
    base = f"https://api.telegram.org/bot{token}"
    try:
        resp = requests.post(f"{base}/setMyCommands", json={"commands": BOT_COMMANDS}, timeout=30)
        data = resp.json()
        if not data.get("ok"):
            log.warning("setMyCommands failed: %s", data)
    except Exception as exc:  # noqa: BLE001
        log.warning("setMyCommands failed: %s", exc)

    short = "IPO fill assistant — personalized GMP & subscription filters"
    about = (
        "IPO Devta helps you decide what to file on closing days.\n\n"
        "Personalized 👍 / 👎 views from your GMP, subscription, and board "
        "filters. Preview the last five processed issues anytime.\n\n"
        "Prefer a shared feed? Join the public channel. "
        "Information only — not investment advice."
    )
    for method, payload in (
        ("setMyShortDescription", {"short_description": short[:120]}),
        ("setMyDescription", {"description": about[:512]}),
    ):
        try:
            resp = requests.post(f"{base}/{method}", json=payload, timeout=30)
            data = resp.json()
            if not data.get("ok"):
                log.warning("%s failed: %s", method, data)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s failed: %s", method, exc)


def _send_home(chat_id: int | str, *, dry_run: bool) -> None:
    prefs = state.get_or_create_user(chat_id)
    notify.send_message(
        chat_id,
        render.welcome_text(prefs),
        reply_markup=keyboards.main_reply_keyboard(),
        dry_run=dry_run,
    )
    notify.send_message(
        chat_id,
        "Quick actions:",
        reply_markup=keyboards.home_inline(),
        dry_run=dry_run,
    )


def _send_help(chat_id: int | str, *, dry_run: bool) -> None:
    notify.send_message(
        chat_id,
        render.help_text(),
        reply_markup=keyboards.home_inline(),
        dry_run=dry_run,
    )


def _send_settings(
    chat_id: int | str,
    *,
    dry_run: bool,
    message_id: int | None = None,
) -> None:
    prefs = state.get_or_create_user(chat_id)
    text = render.settings_text(prefs)
    markup = keyboards.settings_inline(prefs)
    if message_id is not None:
        try:
            notify.edit_message(
                chat_id, message_id, text, reply_markup=markup, dry_run=dry_run
            )
            return
        except notify.NotifyError as exc:
            log.info("edit_message fallback to send: %s", exc)
    notify.send_message(chat_id, text, reply_markup=markup, dry_run=dry_run)


def _send_preview(
    chat_id: int | str,
    *,
    dry_run: bool,
    live_pool: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    prefs = state.get_or_create_user(chat_id)
    pool = live_pool
    # Only fetch live when snapshots are empty
    if pool is None and not preview._latest_unique_snapshots(1):
        pool = preview.load_live_preview_pool(5)
    source, items = preview.build_preview(prefs, limit=5, live_pool=pool)
    text = render.render_preview(prefs, source, items)
    if len(text) > 4000:
        text = text[:3900] + "\n\n…truncated."
    notify.send_message(
        chat_id,
        text,
        reply_markup=keyboards.home_inline(),
        dry_run=dry_run,
    )
    return pool


def _send_channel(chat_id: int | str, *, dry_run: bool) -> None:
    url = keyboards.channel_url()
    notify.send_message(
        chat_id,
        (
            "<b>Public channel</b>\n\n"
            "Daily closing-day GMP feed — no personal filters.\n"
            "Useful if you want reminders without DMs.\n\n"
            f'<a href="{url}">Join {url.replace("https://t.me/", "@")}</a>'
        ),
        reply_markup={"inline_keyboard": [[{"text": "Join channel", "url": url}]]},
        dry_run=dry_run,
    )


def handle_text(
    chat_id: int | str,
    text: str,
    *,
    dry_run: bool,
    live_pool: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    raw = (text or "").strip()
    if not raw:
        return live_pool

    if raw == BTN_PREVIEW:
        return _send_preview(chat_id, dry_run=dry_run, live_pool=live_pool)
    if raw == BTN_SETTINGS:
        _send_settings(chat_id, dry_run=dry_run)
        return live_pool
    if raw == BTN_HELP:
        _send_help(chat_id, dry_run=dry_run)
        return live_pool
    if raw == BTN_CHANNEL:
        _send_channel(chat_id, dry_run=dry_run)
        return live_pool

    parts = raw.split()
    cmd = parts[0].lower().split("@")[0]

    if cmd in ("/start", "start", "/menu", "menu"):
        _send_home(chat_id, dry_run=dry_run)
        return live_pool
    if cmd in ("/help", "help"):
        _send_help(chat_id, dry_run=dry_run)
        return live_pool
    if cmd in ("/preview", "preview") or (
        cmd in ("/gmp", "gmp") and len(parts) < 2
    ):
        return _send_preview(chat_id, dry_run=dry_run, live_pool=live_pool)
    if cmd in ("/gmp", "gmp") and len(parts) >= 2:
        try:
            val = float(parts[1])
        except ValueError:
            notify.send_message(
                chat_id,
                "Use <b>Settings</b> to pick a GMP filter, or tap Preview GMP.",
                reply_markup=keyboards.home_inline(),
                dry_run=dry_run,
            )
            return live_pool
        prefs = state.update_user(chat_id, min_gmp_pct=val)
        notify.send_message(
            chat_id,
            f"<b>Saved</b>\n\n{html_prefs(prefs)}",
            reply_markup=keyboards.settings_inline(prefs),
            dry_run=dry_run,
        )
        return live_pool
    if cmd in ("/settings", "/status", "settings", "status"):
        _send_settings(chat_id, dry_run=dry_run)
        return live_pool
    if cmd in ("/sub", "sub") and len(parts) >= 2:
        try:
            val = float(parts[1])
        except ValueError:
            _send_settings(chat_id, dry_run=dry_run)
            return live_pool
        prefs = state.update_user(chat_id, min_total_sub=val)
        notify.send_message(
            chat_id,
            f"<b>Saved</b>\n\n{html_prefs(prefs)}",
            reply_markup=keyboards.settings_inline(prefs),
            dry_run=dry_run,
        )
        return live_pool
    if cmd in ("/board", "board") and len(parts) >= 2:
        include = parts[1].lower() in ("all", "sme")
        prefs = state.update_user(chat_id, include_sme=include)
        notify.send_message(
            chat_id,
            f"<b>Saved</b>\n\n{html_prefs(prefs)}",
            reply_markup=keyboards.settings_inline(prefs),
            dry_run=dry_run,
        )
        return live_pool
    if cmd in ("/channel", "channel"):
        _send_channel(chat_id, dry_run=dry_run)
        return live_pool

    if cmd.startswith("/"):
        _send_help(chat_id, dry_run=dry_run)
        return live_pool

    notify.send_message(
        chat_id,
        "Use the buttons below — Preview GMP, Settings, Help, or Channel.",
        reply_markup=keyboards.main_reply_keyboard(),
        dry_run=dry_run,
    )
    return live_pool


def html_prefs(prefs: dict[str, Any]) -> str:
    import html as html_mod

    return html_mod.escape(render.prefs_summary(prefs), quote=False)


def handle_callback(
    chat_id: int | str,
    data: str,
    *,
    callback_query_id: str,
    message_id: int | None,
    dry_run: bool,
    live_pool: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    data = (data or "").strip()

    if data in ("home", "menu", "start"):
        notify.answer_callback(callback_query_id, text="Home", dry_run=dry_run)
        _send_home(chat_id, dry_run=dry_run)
        return live_pool
    if data == "help":
        notify.answer_callback(callback_query_id, text="Help", dry_run=dry_run)
        _send_help(chat_id, dry_run=dry_run)
        return live_pool
    if data == "preview":
        notify.answer_callback(callback_query_id, text="Building preview…", dry_run=dry_run)
        return _send_preview(chat_id, dry_run=dry_run, live_pool=live_pool)
    if data == "settings":
        notify.answer_callback(callback_query_id, text="Settings", dry_run=dry_run)
        _send_settings(chat_id, dry_run=dry_run, message_id=message_id)
        return live_pool
    if data == "channel":
        notify.answer_callback(callback_query_id, dry_run=dry_run)
        _send_channel(chat_id, dry_run=dry_run)
        return live_pool

    if data.startswith("gmp:"):
        try:
            val = float(data.split(":", 1)[1])
        except ValueError:
            notify.answer_callback(callback_query_id, text="Invalid GMP", dry_run=dry_run)
            return live_pool
        state.update_user(chat_id, min_gmp_pct=val)
        notify.answer_callback(
            callback_query_id, text=f"Min GMP set to {val:g}%", dry_run=dry_run
        )
        _send_settings(chat_id, dry_run=dry_run, message_id=message_id)
        return live_pool

    if data.startswith("sub:"):
        try:
            val = float(data.split(":", 1)[1])
        except ValueError:
            notify.answer_callback(callback_query_id, text="Invalid sub", dry_run=dry_run)
            return live_pool
        state.update_user(chat_id, min_total_sub=val)
        notify.answer_callback(
            callback_query_id, text=f"Min subscription set to {val:g}x", dry_run=dry_run
        )
        _send_settings(chat_id, dry_run=dry_run, message_id=message_id)
        return live_pool

    if data.startswith("board:"):
        include = data.split(":", 1)[1].lower() in ("all", "sme")
        state.update_user(chat_id, include_sme=include)
        toast = "MAIN + SME" if include else "MAIN only"
        notify.answer_callback(callback_query_id, text=toast, dry_run=dry_run)
        _send_settings(chat_id, dry_run=dry_run, message_id=message_id)
        return live_pool

    notify.answer_callback(callback_query_id, text="Unknown action", dry_run=dry_run)
    return live_pool


def drain_updates(*, dry_run: bool = False) -> int:
    """Process queued Telegram updates. Returns number handled."""
    if not config.telegram_token():
        log.warning("TELEGRAM_TOKEN unset — skip getUpdates")
        return 0

    ensure_bot_commands()

    offset = _load_offset()
    params: dict[str, Any] = {
        "timeout": 0,
        "allowed_updates": '["message","callback_query"]',
    }
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
    live_pool: list[dict[str, Any]] | None = None
    for upd in results:
        uid = upd.get("update_id")
        if uid is not None:
            max_update = uid + 1 if max_update is None else max(max_update, uid + 1)

        cb = upd.get("callback_query")
        if cb:
            chat = ((cb.get("message") or {}).get("chat")) or {}
            chat_id = chat.get("id") or (cb.get("from") or {}).get("id")
            message_id = (cb.get("message") or {}).get("message_id")
            if chat_id is None:
                continue
            try:
                live_pool = handle_callback(
                    chat_id,
                    cb.get("data") or "",
                    callback_query_id=str(cb.get("id")),
                    message_id=message_id,
                    dry_run=dry_run,
                    live_pool=live_pool,
                )
                handled += 1
            except Exception as exc:  # noqa: BLE001
                log.exception("Failed callback from %s: %s", chat_id, exc)
            continue

        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        text = msg.get("text") or ""
        if chat_id is None:
            continue
        try:
            live_pool = handle_text(chat_id, text, dry_run=dry_run, live_pool=live_pool)
            handled += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed handling update from %s: %s", chat_id, exc)

    if max_update is not None and not dry_run:
        _save_offset(max_update)
    return handled
