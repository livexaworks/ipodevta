"""data/*.json state: snapshots and the per-message sent log.

The repo is public, so the sent log never stores raw Telegram chat ids: users are
keyed by an HMAC of the chat id using the EXPORT_SECRET Actions secret.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from bot import config

log = logging.getLogger(__name__)

NO_MATCH = "_none"


def _read(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if text.strip() else default


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _cutoff() -> str:
    return (date.fromisoformat(config.today_ist()) - timedelta(days=config.RETENTION_DAYS)).isoformat()


# --- snapshots -------------------------------------------------------------


def append_snapshots(rows: list[dict[str, Any]]) -> None:
    cutoff = _cutoff()
    kept = [r for r in _read(config.SNAPSHOTS_PATH, []) if str(r.get("date") or "") >= cutoff]
    _write(config.SNAPSHOTS_PATH, kept + rows)


# --- sent log --------------------------------------------------------------


def chat_hash(chat_id: str | int) -> str:
    key = config.worker_secret().encode() or b"local-dev"
    return hmac.new(key, str(chat_id).encode(), hashlib.sha256).hexdigest()[:16]


class SentLog:
    """Load once per run, save after every send so a crash never re-sends."""

    def __init__(self, today: str, path: Path | None = None, *, persist: bool = True) -> None:
        self.path = path or config.SENT_PATH
        self.persist = persist
        raw = _read(self.path, {})
        cutoff = _cutoff()
        # Drop entries older than retention and any pre-v2 shape (which held raw chat ids).
        self.data: dict[str, Any] = {
            k: v
            for k, v in raw.items()
            if _is_date(k) and k >= cutoff and isinstance(v, dict) and "bot" in v
        }
        day = self.data.setdefault(today, {})
        self.channel = day.setdefault("channel", {"header": None, "ipos": {}, "done": None})
        self.bot = day.setdefault("bot", {"users": {}, "done": None})

    def save(self) -> None:
        if self.persist:
            _write(self.path, self.data)

    # channel
    @property
    def header_id(self) -> int | None:
        return self.channel.get("header")

    def set_header(self, message_id: int) -> None:
        self.channel["header"] = message_id
        self.save()

    def channel_sent(self, ipo_id: str) -> bool:
        return ipo_id in self.channel["ipos"]

    def mark_channel(self, ipo_id: str, message_id: int) -> None:
        self.channel["ipos"][ipo_id] = message_id
        self.save()

    # bot
    def dm_sent(self, chat_id: str | int) -> list[str]:
        return list(self.bot["users"].get(chat_hash(chat_id), []))

    def mark_dm(self, chat_id: str | int, item: str) -> None:
        self.bot["users"].setdefault(chat_hash(chat_id), []).append(item)
        self.save()

    # completion
    def done(self, phase: str) -> bool:
        return bool(getattr(self, phase)["done"])

    def mark_done(self, phase: str) -> None:
        getattr(self, phase)["done"] = config.format_ist()
        self.save()


def _is_date(key: str) -> bool:
    try:
        date.fromisoformat(key)
    except ValueError:
        return False
    return True
