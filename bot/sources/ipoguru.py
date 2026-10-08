"""IPO Guru Data API v2: open IPO calendar with GMP (server-side only).

Free plan: 10 requests/day, 1/minute. The bot makes one GET /ipos?status=open
per scheduled run (9:30 channel, 14:30 bot), so 2 calls on a normal day.
Subscription by category comes from BSE (bot/sources/bse.py), not from here.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import requests

from bot import config

log = logging.getLogger(__name__)

USAGE_PATH = config.DATA_DIR / "ipoguru_usage.json"
CACHE_PATH = config.DATA_DIR / "ipoguru_cache.json"
FREE_PLAN_DAILY = 10


class IpoGuruError(RuntimeError):
    pass


class BudgetExceeded(IpoGuruError):
    pass


def api_key() -> str:
    return config.env("IPOGURU_API_KEY")


def base_url() -> str:
    return (config.env("IPOGURU_BASE_URL") or "https://www.ipoguru.in/api/v2").rstrip("/")


def max_requests_per_day() -> int:
    try:
        n = int(config.env("IPOGURU_MAX_REQUESTS_PER_DAY", str(FREE_PLAN_DAILY)))
    except ValueError:
        n = FREE_PLAN_DAILY
    return max(1, min(n, FREE_PLAN_DAILY))


def _parse_number(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    text = str(val).strip().replace("₹", "").replace(",", "").replace("%", "")
    if not text or text.lower() in ("nan", "na", "n/a", "-", "—", "–"):
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def _map_board(ipo_type: Any) -> str | None:
    t = str(ipo_type or "").strip().lower()
    if t in ("mainboard", "main board", "main"):
        return "MAIN"
    if t == "sme":
        return "SME"
    return None


def normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Map one /ipos calendar item into the bot's IPO shape."""
    slug = (row.get("slug") or "").strip()
    board = _map_board(row.get("type"))
    if not slug or board is None:
        return None

    price_high = _parse_number(row.get("price_max"))
    if price_high is None:
        price_high = _parse_number(row.get("issue_price"))
    if price_high is None:
        price_high = _parse_number(row.get("price_band"))

    gmp_block = row.get("gmp") if isinstance(row.get("gmp"), dict) else {}
    gmp_val = _parse_number(gmp_block.get("price"))
    gmp_pct = _parse_number(gmp_block.get("percentage"))
    if gmp_pct is None and gmp_val is not None and price_high:
        gmp_pct = round(gmp_val / price_high * 100, 2)

    return {
        "ipo_id": slug,
        "name": (row.get("display_name") or row.get("name") or slug).strip(),
        "board": board,
        "price_high": price_high,
        "open_date": row.get("open_date"),
        "close_date": row.get("close_date"),
        "gmp": gmp_val,
        "gmp_pct": gmp_pct,
        "gmp_updated_label": gmp_block.get("updated_at_label"),
        "sub_total": _parse_number(row.get("subscription_total")),
        "sub_qib": None,
        "sub_nii": None,
        "sub_retail": None,
        "sub_source": "ipoguru",
        "web_url": row.get("web_url"),
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def usage_today() -> dict[str, Any]:
    today = config.today_ist()
    data = _load_json(USAGE_PATH) or {}
    if data.get("date") != today:
        return {"date": today, "requests": 0, "last_ts": 0.0}
    return {
        "date": today,
        "requests": int(data.get("requests") or 0),
        "last_ts": float(data.get("last_ts") or 0),
    }


def usage_remaining() -> int:
    return max(0, max_requests_per_day() - usage_today()["requests"])


def _record_usage() -> None:
    u = usage_today()
    u["requests"] += 1
    u["last_ts"] = time.time()
    _save_json(USAGE_PATH, u)


def _today_cache() -> list[dict[str, Any]] | None:
    data = _load_json(CACHE_PATH)
    if not data or data.get("date") != config.today_ist():
        return None
    rows = data.get("ipos")
    return rows if isinstance(rows, list) else None


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    key = api_key()
    if not key:
        raise IpoGuruError("IPOGURU_API_KEY is not set")

    u = usage_today()
    if u["requests"] >= max_requests_per_day():
        raise BudgetExceeded(
            f"daily budget used ({u['requests']}/{max_requests_per_day()} on {u['date']} IST)"
        )
    elapsed = time.time() - u["last_ts"]
    if u["last_ts"] and elapsed < 61:
        log.info("IPO Guru: waiting %.0fs for the 1/min limit", 61 - elapsed)
        time.sleep(61 - elapsed)

    log.info("IPO Guru GET %s %s (used %d/%d today)", path, params, u["requests"], max_requests_per_day())
    resp = requests.get(
        f"{base_url()}{path}",
        headers={"X-API-KEY": key, "Accept": "application/json", "User-Agent": config.USER_AGENT},
        params=params,
        timeout=30,
    )
    _record_usage()  # the provider meters failed attempts too

    if resp.status_code == 429:
        raise IpoGuruError(f"429 rate limited; Retry-After={resp.headers.get('Retry-After', '?')}")
    if resp.status_code == 401:
        raise IpoGuruError("401 unauthorized: check IPOGURU_API_KEY")
    if resp.status_code >= 400:
        raise IpoGuruError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise IpoGuruError("malformed JSON response") from exc
    if not isinstance(payload, dict) or not payload.get("success"):
        raise IpoGuruError(f"API success=false: {str(payload)[:300]}")
    return payload


def fetch_open_ipos() -> list[dict[str, Any]]:
    """Open IPOs with GMP. One network call; reuses today's cache if the budget is spent."""
    try:
        raw = _get("/ipos", {"status": "open"})
    except BudgetExceeded:
        cached = _today_cache()
        if cached is None:
            raise
        log.warning("IPO Guru budget spent: reusing today's cache (%d IPOs)", len(cached))
        return cached

    data = raw.get("data")
    if not isinstance(data, list):
        raise IpoGuruError("/ipos missing data array")

    ipos = []
    for row in data:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip().lower() not in ("", "open"):
            continue
        norm = normalize_row(row)
        if norm:
            ipos.append(norm)

    _save_json(
        CACHE_PATH,
        {"fetched_at": config.format_ist(), "date": config.today_ist(), "count": len(ipos), "ipos": ipos},
    )
    log.info("IPO Guru: %d open IPOs (plan=%s)", len(ipos), raw.get("plan"))
    return ipos
