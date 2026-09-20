"""NSE upcoming issues - optional fallback; failure must not break the run."""

from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger(__name__)


def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "application/json, text/plain, */*",
        }
    )
    s.get("https://www.nseindia.com/", timeout=15)
    s.get("https://www.nseindia.com/market-data/all-upcoming-issues-ipo", timeout=15)
    return s


def fetch_upcoming() -> list[dict[str, Any]]:
    try:
        s = nse_session()
        resp = s.get(
            "https://www.nseindia.com/api/all-upcoming-issues?category=ipo",
            timeout=20,
        )
        if resp.status_code != 200:
            log.warning("NSE upcoming HTTP %s - skipping", resp.status_code)
            return []
        data = resp.json()
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("data", "Data", "issues", "list"):
                val = data.get(key)
                if isinstance(val, list):
                    return [x for x in val if isinstance(x, dict)]
        return []
    except Exception as exc:  # noqa: BLE001
        log.warning("NSE upcoming failed (non-fatal): %s", exc)
        return []
