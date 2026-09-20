"""Disk cache for live preview IPO pools (shared across Actions runs)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from bot import config

log = logging.getLogger(__name__)

POOL_PATH = config.DATA_DIR / "preview_pool.json"
POOL_TTL_SEC = 45 * 60  # reuse market fetch for 45 minutes


def _read_pool() -> dict[str, Any] | None:
    if not POOL_PATH.is_file():
        return None
    try:
        data = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    return data


def load_cached_live_pool(limit: int = 5) -> list[dict[str, Any]] | None:
    data = _read_pool()
    if not data:
        return None
    ts = float(data.get("ts") or 0)
    if time.time() - ts > POOL_TTL_SEC:
        return None
    rows = data.get("ipos")
    if not isinstance(rows, list) or not rows:
        return None
    log.info("Using cached live preview pool (%d rows, age %.0fs)", len(rows), time.time() - ts)
    return rows[:limit]


def save_live_pool(ipos: list[dict[str, Any]]) -> None:
    POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": time.time(),
        "saved_at": config.format_ist(),
        "ipos": ipos,
    }
    POOL_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("Saved live preview pool (%d rows)", len(ipos))


def prefs_fingerprint(prefs: dict[str, Any]) -> dict[str, Any]:
    return {
        "min_gmp_pct": float(prefs.get("min_gmp_pct", config.MIN_GMP_PCT)),
        "min_total_sub": float(prefs.get("min_total_sub", config.MIN_TOTAL_SUB)),
        "include_sme": bool(prefs.get("include_sme", config.INCLUDE_SME)),
    }


def publish_user_preview(
    chat_id: str | int,
    text: str,
    prefs: dict[str, Any],
    *,
    source: str,
) -> bool:
    """Push rendered preview to the Worker so repeat taps are instant."""
    base = config.webhook_base_url().rstrip("/")
    secret = config.webhook_export_secret()
    if not base or not secret:
        return False
    try:
        resp = requests.post(
            f"{base}/cache/preview",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            json={
                "chat_id": str(chat_id),
                "text": text,
                "prefs": prefs_fingerprint(prefs),
                "source": source,
                "saved_at": config.format_ist(),
            },
            timeout=20,
        )
        if resp.status_code >= 300:
            log.warning("publish_user_preview failed: %s %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_user_preview error: %s", exc)
        return False
