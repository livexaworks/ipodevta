"""Read/write data/*.json - snapshots, sent log, user prefs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from bot import config

log = logging.getLogger(__name__)


def _read(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return default
    return json.loads(text)


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_snapshots() -> list[dict[str, Any]]:
    data = _read(config.SNAPSHOTS_PATH, [])
    if not isinstance(data, list):
        raise ValueError("snapshots.json must be a list")
    return data


def save_snapshots(rows: list[dict[str, Any]]) -> None:
    cutoff = (config.now_ist() - timedelta(days=config.SNAPSHOT_RETENTION_DAYS)).date()
    pruned: list[dict[str, Any]] = []
    for row in rows:
        d = row.get("date")
        if not d:
            pruned.append(row)
            continue
        try:
            row_date = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            pruned.append(row)
            continue
        if row_date >= cutoff:
            pruned.append(row)
    _write(config.SNAPSHOTS_PATH, pruned)


def append_snapshots(new_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = load_snapshots()
    rows.extend(new_rows)
    save_snapshots(rows)
    return rows


def load_sent() -> dict[str, Any]:
    data = _read(config.SENT_PATH, {})
    if not isinstance(data, dict):
        raise ValueError("sent.json must be an object")
    return data


def save_sent(data: dict[str, Any]) -> None:
    _write(config.SENT_PATH, data)


def channel_already_sent(date: str) -> bool:
    sent = load_sent()
    entry = sent.get(date)
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("channel"))


def user_already_sent(date: str, chat_id: str | int) -> bool:
    sent = load_sent()
    entry = sent.get(date)
    if not isinstance(entry, dict):
        return False
    users = entry.get("users") or {}
    return str(chat_id) in users


def mark_channel_sent(date: str, ipo_ids: list[str]) -> None:
    sent = load_sent()
    entry = sent.setdefault(date, {"ts": config.format_ist(), "channel": None, "users": {}})
    if not isinstance(entry.get("users"), dict):
        entry["users"] = {}
    entry["channel"] = {"ts": config.format_ist(), "ipo_ids": ipo_ids}
    entry["ts"] = config.format_ist()
    save_sent(sent)


def mark_user_sent(date: str, chat_id: str | int, ipo_ids: list[str]) -> None:
    sent = load_sent()
    entry = sent.setdefault(date, {"ts": config.format_ist(), "channel": None, "users": {}})
    if not isinstance(entry.get("users"), dict):
        entry["users"] = {}
    entry["users"][str(chat_id)] = {"ts": config.format_ist(), "ipo_ids": ipo_ids}
    entry["ts"] = config.format_ist()
    save_sent(sent)


def load_users() -> dict[str, Any]:
    """Prefer live webhook prefs (instant Settings), else data/users.json."""
    try:
        from bot import webhook_users

        remote = webhook_users.fetch_users()
        if remote is not None:
            # Keep a local mirror so the repo still has a backup after alerts
            try:
                save_users(remote)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not mirror webhook users locally: %s", exc)
            return remote
    except Exception as exc:  # noqa: BLE001
        log.warning("webhook user load skipped: %s", exc)

    data = _read(config.USERS_PATH, {})
    if not isinstance(data, dict):
        raise ValueError("users.json must be an object")
    return data


def save_users(data: dict[str, Any]) -> None:
    _write(config.USERS_PATH, data)


def default_prefs() -> dict[str, Any]:
    return {
        "min_gmp_pct": config.MIN_GMP_PCT,
        "min_total_sub": config.MIN_TOTAL_SUB,
        "include_sme": config.INCLUDE_SME,
        "updated": config.format_ist(),
    }


def get_or_create_user(chat_id: str | int) -> dict[str, Any]:
    users = load_users()
    key = str(chat_id)
    if key not in users:
        users[key] = default_prefs()
        save_users(users)
    return users[key]


def update_user(chat_id: str | int, **fields: Any) -> dict[str, Any]:
    users = load_users()
    key = str(chat_id)
    prefs = users.get(key) or default_prefs()
    prefs.update(fields)
    prefs["updated"] = config.format_ist()
    users[key] = prefs
    save_users(users)
    return prefs
