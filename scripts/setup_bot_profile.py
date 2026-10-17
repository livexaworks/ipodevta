#!/usr/bin/env python3
"""Idempotent Telegram bot profile setup from shared/copy.json.

    python scripts/setup_bot_profile.py

Reads TELEGRAM_TOKEN from the environment / .env, calls setMyName,
setMyShortDescription, setMyDescription, setMyCommands, then verifies with
the matching get* methods. Exits non-zero on any mismatch.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot import config  # noqa: E402
from bot.profile import setup_and_verify  # noqa: E402


def main() -> int:
    config.load_dotenv()
    token = config.telegram_token()
    if not token:
        print("TELEGRAM_TOKEN missing", file=sys.stderr)
        return 1
    return setup_and_verify(token)


if __name__ == "__main__":
    raise SystemExit(main())
