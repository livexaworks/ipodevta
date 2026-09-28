"""IPO Guru Data API v2 — calendar + GMP (server-side only).

Hybrid bot layout:
  - This module: open IPO list + GMP (free plan: 10 req/day, 1/min)
  - bot/sources/bse.py: QIB/NII/Retail from BSE public APIs (no Guru quota)

Prefer one GET /ipos?status=open per collect. Preview/commands use disk cache
and do not call the network. Never put the API key in browser/Worker/client code.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

from bot import config

log = logging.getLogger(__name__)

USAGE_PATH = config.DATA_DIR / "ipoguru_usage.json"
CACHE_PATH = config.DATA_DIR / "ipoguru_cache.json"

SOURCE = "ipoguru"


class IpoGuruError(RuntimeError):
    pass


class BudgetExceeded(IpoGuruError):
    pass


class RateLimited(IpoGuruError):
    pass


def api_key() -> str:
    config.load_dotenv()
    return os.environ.get("IPOGURU_API_KEY", "").strip()


def base_url() -> str:
    config.load_dotenv()
    return (
        os.environ.get("IPOGURU_BASE_URL", "").strip()
        or "https://www.ipoguru.in/api/v2"
    ).rstrip("/")


def max_requests_per_day() -> int:
    config.load_dotenv()
    raw = os.environ.get("IPOGURU_MAX_REQUESTS_PER_DAY", "10").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 10
    return max(1, min(n, 10))  # free-plan ceiling


def _parse_number(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    text = str(val).strip()
    if not text or text.lower() in ("nan", "na", "n/a", "-", "—", "–"):
        return None
    text = text.replace("₹", "").replace(",", "").replace("%", "")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _map_board(ipo_type: Any) -> str | None:
    if ipo_type is None:
        return None
    t = str(ipo_type).strip().lower()
    if t in ("mainboard", "main board", "main"):
        return "MAIN"
    if t == "sme":
        return "SME"
    return None


def normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Map one /ipos calendar item into the bot's snapshot/IPO shape."""
    slug = (row.get("slug") or "").strip()
    if not slug:
        return None
    board = _map_board(row.get("type"))
    if board is None:
        return None

    name = (row.get("display_name") or row.get("name") or slug).strip()
    price_high = row.get("price_max")
    if price_high is None:
        price_high = _parse_number(row.get("issue_price"))
    if price_high is None:
        price_high = _parse_number(row.get("price_band"))

    gmp_block = row.get("gmp") if isinstance(row.get("gmp"), dict) else {}
    gmp_val = _parse_number(gmp_block.get("price"))
    gmp_pct = _parse_number(gmp_block.get("percentage"))
    if gmp_pct is None and gmp_val is not None and price_high:
        gmp_pct = round(gmp_val / float(price_high) * 100, 2)

    # Authoritative licensed feed → treat as high confidence (single source).
    has_gmp = gmp_val is not None
    confidence = "high" if has_gmp else None

    return {
        "ipo_id": slug,
        "slug": slug,
        "name": name,
        "board": board,
        "price_high": float(price_high) if price_high is not None else None,
        "lot_size": row.get("lot_size"),
        "close_date": row.get("close_date"),
        "open_date": row.get("open_date"),
        "ipo_no": None,
        "web_url": row.get("web_url"),
        "gmp": gmp_val,
        "gmp_pct": gmp_pct,
        "n_sources": 1 if has_gmp else 0,
        "spread_pct": 0.0 if has_gmp else None,
        "confidence": confidence,
        "sub_total": _parse_number(row.get("subscription_total")),
        "sub_qib": None,  # category book is Standard+ on IPO Guru
        "sub_nii": None,
        "sub_retail": None,
        "gmp_updated_at": gmp_block.get("updated_at"),
        "gmp_updated_label": gmp_block.get("updated_at_label"),
        "source": SOURCE,
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _usage_today() -> dict[str, Any]:
    today = config.today_ist()
    data = _load_json(USAGE_PATH) or {}
    if data.get("date") != today:
        return {"date": today, "requests": 0, "last_ts": 0.0, "paths": []}
    return {
        "date": today,
        "requests": int(data.get("requests") or 0),
        "last_ts": float(data.get("last_ts") or 0),
        "paths": list(data.get("paths") or []),
    }


def usage_remaining() -> int:
    u = _usage_today()
    return max(0, max_requests_per_day() - int(u["requests"]))


def load_cached_ipos() -> list[dict[str, Any]] | None:
    """Return last successful normalized IPO list (any day), or None."""
    data = _load_json(CACHE_PATH)
    if not data:
        return None
    rows = data.get("ipos")
    if not isinstance(rows, list) or not rows:
        return None
    return rows


def _save_cache(raw: dict[str, Any], ipos: list[dict[str, Any]]) -> None:
    _save_json(
        CACHE_PATH,
        {
            "fetched_at": config.format_ist(),
            "date": config.today_ist(),
            "path": "/ipos",
            "params": {"status": "open"},
            "count": len(ipos),
            "raw_count": raw.get("count"),
            "plan": raw.get("plan"),
            "ipos": ipos,
        },
    )


def _record_usage(path: str) -> None:
    u = _usage_today()
    u["requests"] = int(u["requests"]) + 1
    u["last_ts"] = time.time()
    paths = list(u.get("paths") or [])
    paths.append({"path": path, "ts": config.format_ist()})
    u["paths"] = paths[-20:]
    _save_json(USAGE_PATH, u)


def _wait_for_minute_budget(last_ts: float) -> None:
    """Free plan: 1 request / minute."""
    if not last_ts:
        return
    elapsed = time.time() - last_ts
    if elapsed < 61:
        wait = 61 - elapsed
        log.info("IPO Guru: waiting %.0fs for 1/min limit", wait)
        time.sleep(wait)


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    key = api_key()
    if not key:
        raise IpoGuruError("IPOGURU_API_KEY is not set")

    u = _usage_today()
    if int(u["requests"]) >= max_requests_per_day():
        raise BudgetExceeded(
            f"IPO Guru daily budget exhausted "
            f"({u['requests']}/{max_requests_per_day()} on {u['date']} IST). "
            "Using cache only until midnight IST."
        )

    _wait_for_minute_budget(float(u.get("last_ts") or 0))

    url = f"{base_url()}{path}"
    headers = {
        "X-API-KEY": key,
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT,
    }
    log.info("IPO Guru GET %s params=%s (used %s/%s today)", path, params, u["requests"], max_requests_per_day())
    resp = requests.get(url, headers=headers, params=params or {}, timeout=30)

    # Count the attempt toward budget even on errors (provider meters them).
    _record_usage(path)

    if resp.status_code == 429:
        retry = resp.headers.get("Retry-After", "?")
        raise RateLimited(f"429 rate limited; Retry-After={retry}")
    if resp.status_code == 401:
        raise IpoGuruError("401 unauthorized — check IPOGURU_API_KEY")
    if resp.status_code == 402:
        raise IpoGuruError(f"402 plan scope required: {resp.text[:300]}")
    if resp.status_code >= 400:
        raise IpoGuruError(f"HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise IpoGuruError("malformed JSON response") from exc

    if not isinstance(payload, dict) or not payload.get("success"):
        raise IpoGuruError(f"API success=false: {str(payload)[:300]}")

    remaining = resp.headers.get("X-RateLimit-Remaining")
    if remaining is not None:
        log.info("IPO Guru X-RateLimit-Remaining=%s", remaining)
    return payload


def fetch_open_ipos(*, allow_network: bool = True) -> list[dict[str, Any]]:
    """
    Open IPO calendar with GMP (one request when allow_network=True).

    Preview / commands must pass allow_network=False and rely on disk cache
    written by alert/snapshot — keeps us at 2 scheduled calls/day.
    """
    if not allow_network:
        cached = load_cached_ipos()
        if cached is None:
            raise IpoGuruError("No IPO Guru cache yet; wait for the next alert/snapshot run")
        log.info("IPO Guru: using disk cache (%d IPOs, no network)", len(cached))
        return cached

    try:
        raw = _get("/ipos", {"status": "open", "months": 3})
    except BudgetExceeded:
        cached = load_cached_ipos()
        if cached is not None:
            log.warning("IPO Guru budget hit — falling back to disk cache (%d IPOs)", len(cached))
            return cached
        raise

    data = raw.get("data")
    if not isinstance(data, list):
        raise IpoGuruError("/ipos missing data array")

    ipos: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status and status != "open":
            continue
        norm = normalize_row(row)
        if norm:
            ipos.append(norm)

    if not ipos:
        raise IpoGuruError("/ipos returned zero open equity IPOs")

    _save_cache(raw, ipos)
    log.info("IPO Guru: %d open IPOs (plan=%s)", len(ipos), raw.get("plan"))
    return ipos
