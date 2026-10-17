"""One-time Telegram setup for the Cloudflare Worker bot.

    python -m bot.set_webhook set --url https://ipogmpalerts.<you>.workers.dev
    python -m bot.set_webhook profile      # commands, name, descriptions from shared/copy.json
    python -m bot.set_webhook info
    python -m bot.set_webhook delete
"""

from __future__ import annotations

import argparse
import sys

import requests

from bot import config
from bot.profile import apply_profile, setup_and_verify


def _post(api: str, method: str, payload: dict) -> bool:
    data = requests.post(f"{api}/{method}", json=payload, timeout=30).json()
    print(method, data)
    return bool(data.get("ok"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the Telegram webhook and bot profile")
    parser.add_argument("action", choices=("set", "profile", "info", "delete"))
    parser.add_argument("--url", help="Worker base URL, e.g. https://ipogmpalerts.example.workers.dev")
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="profile: set only, skip get* verification",
    )
    args = parser.parse_args(argv)

    token = config.telegram_token()
    if not token:
        print("TELEGRAM_TOKEN missing", file=sys.stderr)
        return 1
    api = f"https://api.telegram.org/bot{token}"

    if args.action == "info":
        print(requests.get(f"{api}/getWebhookInfo", timeout=30).json())
        return 0
    if args.action == "delete":
        return 0 if _post(api, "deleteWebhook", {"drop_pending_updates": False}) else 1
    if args.action == "profile":
        if args.no_verify:
            try:
                apply_profile(token)
            except Exception as exc:  # noqa: BLE001
                print(exc, file=sys.stderr)
                return 1
            return 0
        return setup_and_verify(token)

    base = (args.url or config.worker_base_url()).rstrip("/")
    if not base:
        print("Pass --url or set WEBHOOK_BASE_URL", file=sys.stderr)
        return 1
    payload = {
        "url": f"{base}/telegram",
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": False,
    }
    secret = config.env("WEBHOOK_SECRET")
    if secret:
        payload["secret_token"] = secret
    return 0 if _post(api, "setWebhook", payload) else 1


if __name__ == "__main__":
    raise SystemExit(main())
