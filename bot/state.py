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


def brief_key(chat_id: str | int, date: str) -> str:
    return f"brief:{chat_id}:{date}"


def channel_key(date: str) -> str:
    return f"channel:{date}"


def channel_already_sent(date: str) -> bool:
    sent = load_sent()
    entry = sent.get(channel_key(date))
    return bool(entry)


def brief_already_sent(date: str, chat_id: str | int) -> bool:
    sent = load_sent()
    return brief_key(chat_id, date) in sent


def alert_already_ran(date: str) -> bool:
    """True when today's channel post or any brief is already in sent.json."""
    sent = load_sent()
    if channel_key(date) in sent:
        return True
    suffix = f":{date}"
    return any(
        isinstance(k, str) and k.startswith("brief:") and k.endswith(suffix)
        for k in sent
    )


# Back-compat alias used by older call sites
def user_already_sent(date: str, chat_id: str | int) -> bool:
    return brief_already_sent(date, chat_id)


def latest_ipos_for_date(date: str) -> list[dict[str, Any]]:
    """Latest snapshot row per ipo_id for a given IST date — no network."""
    by_id: dict[str, dict[str, Any]] = {}
    for row in load_snapshots():
        if row.get("date") != date:
            continue
        iid = row.get("ipo_id")
        if not iid:
            continue
        cur = by_id.get(str(iid))
        if cur is None or (row.get("ts") or "") > (cur.get("ts") or ""):
            by_id[str(iid)] = row
    return list(by_id.values())


def mark_channel_sent(date: str, ipo_ids: list[str]) -> None:
    sent = load_sent()
    sent[channel_key(date)] = {
        "ts": config.format_ist(),
        "ipo_ids": ipo_ids,
    }
    save_sent(sent)


def mark_brief_sent(
    date: str,
    chat_id: str | int,
    *,
    ipo_ids: list[str] | None = None,
    quiet: bool = False,
) -> None:
    sent = load_sent()
    sent[brief_key(chat_id, date)] = {
        "ts": config.format_ist(),
        "ipo_ids": ipo_ids or [],
        "quiet": quiet,
    }
    save_sent(sent)


# Back-compat alias
def mark_user_sent(date: str, chat_id: str | int, ipo_ids: list[str]) -> None:
    mark_brief_sent(date, chat_id, ipo_ids=ipo_ids)


def load_users_file() -> dict[str, Any]:
    data = _read(config.USERS_PATH, {})
    if not isinstance(data, dict):
        raise ValueError("users.json must be an object")
    return data


def load_users() -> dict[str, Any]:
    """Prefer live webhook prefs for alerts; else data/users.json."""
    try:
        from bot import webhook_users

        remote = webhook_users.fetch_users()
        if remote is not None:
            try:
                save_users(remote)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not mirror webhook users locally: %s", exc)
            return remote
    except Exception as exc:  # noqa: BLE001
        log.warning("webhook user load skipped: %s", exc)

    return load_users_file()


def save_users(data: dict[str, Any]) -> None:
    _write(config.USERS_PATH, data)


def default_prefs() -> dict[str, Any]:
    return {
        "board": "main",
        "min_gmp_main": config.MIN_GMP_MAIN,
        "min_gmp_sme": config.MIN_GMP_SME,
        "min_gmp_pct": config.MIN_GMP_MAIN,
        "min_total_sub": config.MIN_TOTAL_SUB,
        "include_sme": config.INCLUDE_SME,
        "awaiting_input": None,
        "updated": config.format_ist(),
    }


def get_or_create_user(chat_id: str | int) -> dict[str, Any]:
    key = str(chat_id)
    # Read path: webhook (if configured) so Preview/alert see live Settings
    try:
        from bot import webhook_users

        remote = webhook_users.fetch_users()
        if remote is not None and key in remote:
            return remote[key]
    except Exception:  # noqa: BLE001
        pass

    users = load_users_file()
    if key not in users:
        users[key] = default_prefs()
        save_users(users)
    return users[key]


def update_user(chat_id: str | int, **fields: Any) -> dict[str, Any]:
    """Local file update (tests / legacy). Live Settings are owned by the Worker."""
    users = load_users_file()
    key = str(chat_id)
    prefs = users.get(key) or default_prefs()
    prefs.update(fields)
    prefs["updated"] = config.format_ist()
    users[key] = prefs
    save_users(users)
    return prefs
