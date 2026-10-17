#!/usr/bin/env python3
"""Production smoke checks for IPO GMP Alerts.

    python scripts/check_prod.py

Checks env presence, Bot API identity/profile, webhook URL, Worker /health,
and that slash commands still respond (posts /help to ADMIN_CHAT_ID via the
live webhook path).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

from bot import config, copy
from bot.profile import verify_profile

REQUIRED_ENV = (
    "TELEGRAM_TOKEN",
    "CHANNEL_ID",
    "CHANNEL_USERNAME",
    "BOT_USERNAME",
    "ADMIN_CHAT_ID",
    "WEBHOOK_BASE_URL",
    "WEBHOOK_SECRET",
    "EXPORT_SECRET",
)


def _ok(msg: str) -> None:
    print(f"OK  {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL  {msg}", file=sys.stderr)


def check_env() -> list[str]:
    errors: list[str] = []
    config.load_dotenv()
    for key in REQUIRED_ENV:
        if not config.env(key):
            errors.append(f"missing env {key}")
        else:
            _ok(f"env {key} set")
    channel = config.channel_username()
    bot = config.bot_username()
    if channel != "ipogmpalerts":
        errors.append(f"CHANNEL_USERNAME={channel!r} expected ipogmpalerts")
    else:
        _ok("CHANNEL_USERNAME=ipogmpalerts")
    if bot != "ipogmpalertsbot":
        errors.append(f"BOT_USERNAME={bot!r} expected ipogmpalertsbot")
    else:
        _ok("BOT_USERNAME=ipogmpalertsbot")
    return errors


def check_bot_identity(token: str) -> list[str]:
    errors: list[str] = []
    data = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=30).json()
    if not data.get("ok"):
        return [f"getMe failed: {data}"]
    me = data["result"]
    want = config.bot_username()
    got = me.get("username") or ""
    if got.lower() != want.lower():
        errors.append(f"getMe username @{got} != @{want}")
    else:
        _ok(f"getMe @{got} (id={me.get('id')})")
    if not me.get("can_join_groups") and me.get("can_join_groups") is not None:
        pass  # informational only for channels
    return errors


def check_webhook(token: str) -> list[str]:
    errors: list[str] = []
    data = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=30).json()
    if not data.get("ok"):
        return [f"getWebhookInfo failed: {data}"]
    info = data["result"]
    want = config.worker_base_url().rstrip("/") + "/telegram"
    got = (info.get("url") or "").rstrip("/")
    if got != want:
        errors.append(f"webhook url {got!r} != {want!r}")
    else:
        _ok(f"webhook {got}")
    pending = info.get("pending_update_count") or 0
    if pending > 50:
        errors.append(f"webhook backlog high: {pending} pending updates")
    else:
        _ok(f"webhook pending_update_count={pending}")
    if info.get("last_error_message"):
        _fail(f"webhook last_error: {info.get('last_error_message')} at {info.get('last_error_date')}")
        # Soft fail: surface but do not block if URL is correct (transient Telegram blips).
    return errors


def check_profile(token: str) -> list[str]:
    try:
        verify_profile(token)
        _ok("bot profile matches shared/copy.json")
        return []
    except Exception as exc:  # noqa: BLE001
        return [f"profile: {exc}"]


def check_worker_health() -> list[str]:
    base = config.worker_base_url().rstrip("/")
    try:
        resp = requests.get(f"{base}/health", timeout=20)
    except requests.RequestException as exc:
        return [f"worker /health request failed: {exc}"]
    if resp.status_code != 200 or resp.text.strip() != "ok":
        return [f"worker /health -> {resp.status_code} {resp.text!r}"]
    _ok(f"worker /health ok ({base})")
    return []


def check_command_via_webhook() -> list[str]:
    """POST a synthetic /help update through the live Worker webhook."""
    admin = config.admin_chat_id()
    if not admin:
        return ["ADMIN_CHAT_ID missing; cannot smoke-test commands"]
    try:
        chat_id = int(admin)
    except ValueError:
        chat_id = admin
    base = config.worker_base_url().rstrip("/")
    secret = config.env("WEBHOOK_SECRET")
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False, "first_name": "ProdCheck"},
            "text": "/help",
        },
    }
    headers = {"content-type": "application/json"}
    if secret:
        headers["x-telegram-bot-api-secret-token"] = secret
    try:
        resp = requests.post(f"{base}/telegram", headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        return [f"webhook /help POST failed: {exc}"]
    if resp.status_code != 200:
        return [f"webhook /help -> HTTP {resp.status_code} {resp.text[:200]!r}"]
    _ok("webhook accepted /help (Worker returned 200; help should arrive in ADMIN chat)")
    return []


def check_commands_menu(token: str) -> list[str]:
    want = set(copy.load()["commands"])
    data = requests.get(f"https://api.telegram.org/bot{token}/getMyCommands", timeout=30).json()
    if not data.get("ok"):
        return [f"getMyCommands failed: {data}"]
    got = {c["command"] for c in data["result"]}
    if got != want:
        return [f"commands menu {sorted(got)} != {sorted(want)}"]
    _ok(f"commands menu: {', '.join(sorted(got))}")
    return []


def main() -> int:
    config.load_dotenv()
    errors: list[str] = []
    errors += check_env()
    token = config.telegram_token()
    if not token:
        _fail("TELEGRAM_TOKEN missing; aborting remaining checks")
        return 1

    errors += check_bot_identity(token)
    errors += check_webhook(token)
    errors += check_commands_menu(token)
    errors += check_profile(token)
    errors += check_worker_health()
    errors += check_command_via_webhook()

    print()
    if errors:
        for e in errors:
            _fail(e)
        print(f"\n{len(errors)} check(s) failed")
        return 1
    print("all production checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
