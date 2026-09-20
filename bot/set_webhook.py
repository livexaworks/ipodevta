"""Register or remove the Telegram webhook pointing at the Cloudflare Worker."""

from __future__ import annotations

import argparse
import sys

import requests

from bot import config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Telegram webhook")
    parser.add_argument(
        "action",
        choices=("set", "delete", "info"),
        help="set webhook URL, delete webhook (back to polling), or show info",
    )
    parser.add_argument(
        "--url",
        help="Worker URL base, e.g. https://ipo-devta-bot.example.workers.dev",
    )
    args = parser.parse_args(argv)
    config.load_dotenv()
    token = config.telegram_token()
    if not token:
        print("TELEGRAM_TOKEN missing", file=sys.stderr)
        return 1

    api = f"https://api.telegram.org/bot{token}"
    if args.action == "info":
        r = requests.get(f"{api}/getWebhookInfo", timeout=30)
        print(r.json())
        return 0

    if args.action == "delete":
        r = requests.post(f"{api}/deleteWebhook", json={"drop_pending_updates": False}, timeout=30)
        print(r.json())
        return 0 if r.json().get("ok") else 1

    base = (args.url or config.webhook_base_url()).rstrip("/")
    if not base:
        print("Pass --url or set WEBHOOK_BASE_URL", file=sys.stderr)
        return 1
    secret = config.webhook_secret()
    payload = {
        "url": f"{base}/telegram",
        "allowed_updates": ["message", "callback_query", "edited_message"],
        "drop_pending_updates": False,
    }
    if secret:
        payload["secret_token"] = secret
    r = requests.post(f"{api}/setWebhook", json=payload, timeout=30)
    print(r.json())
    return 0 if r.json().get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
