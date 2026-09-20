"""BSE live IPOs + category subscription (parsers from live discover fixtures)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import requests

from bot import config

# Confirmed against fixtures/bse_live.json and fixtures/bse_catdem_7973.json (2026-09-20)


class BseError(RuntimeError):
    pass


class SourceBroken(RuntimeError):
    pass


def fetch_live() -> Any:
    resp = requests.get(config.BSE_LIVE, headers=config.BSE_HEADERS, timeout=30)
    if resp.status_code != 200:
        raise BseError(f"BSE_LIVE HTTP {resp.status_code}")
    try:
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        raise BseError("BSE_LIVE returned malformed JSON") from exc


def fetch_catdem(ipo_no: str | int) -> Any | None:
    """Try classic CATDEM then NEW. Both empty → None (missing, not zero)."""
    for template in (config.BSE_CATDEM, config.BSE_CATDEM_NEW):
        url = template.format(ipo_no=ipo_no)
        try:
            resp = requests.get(url, headers=config.BSE_HEADERS, timeout=30)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if _catdem_has_rows(data):
                return data
        except Exception:  # noqa: BLE001
            continue
    return None


def _catdem_has_rows(data: Any) -> bool:
    rows = _catdem_rows(data)
    # need more than a header-only table
    return len(rows) > 1


def _catdem_rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    table = data.get("table1") or data.get("Table1") or data.get("Table")
    if not isinstance(table, list):
        return []
    return [r for r in table if isinstance(r, dict)]


def parse_price_high(price_band: Any) -> float | None:
    if price_band is None:
        return None
    text = str(price_band).strip()
    if not text:
        return None
    nums = re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))
    if not nums:
        return None
    return float(nums[-1])


def parse_close_date(end_dt: Any) -> str | None:
    if not end_dt:
        return None
    text = str(end_dt).strip()
    # "2026-09-21T00:00:00" or with time
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def map_board(platform: Any) -> str | None:
    if platform is None:
        return None
    p = str(platform).strip().lower()
    if p in ("mainboard", "main board", "main"):
        return "MAIN"
    if p == "sme":
        return "SME"
    return None  # Debt / unknown — not equity IPO boards we screen


def parse_live(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or "Table" not in payload:
        raise BseError("BSE_LIVE missing Table")
    table = payload["Table"]
    if not isinstance(table, list) or len(table) == 0:
        raise SourceBroken("BSE_LIVE returned zero live issues")

    out: list[dict[str, Any]] = []
    for row in table:
        if not isinstance(row, dict):
            continue
        ir = str(row.get("IR_flag") or "").upper()
        if ir != "IPO":
            continue
        board = map_board(row.get("eXCHANGE_PLATFORM"))
        if board is None:
            continue
        ipo_no = row.get("IPO_NO")
        if ipo_no is None:
            continue
        name = row.get("LONG_NAME") or row.get("Scrip_Name") or row.get("short_name")
        if not name:
            continue
        out.append(
            {
                "ipo_no": str(ipo_no),
                "scrip_cd": row.get("Scrip_cd"),
                "name": str(name).strip(),
                "board": board,
                "price_high": parse_price_high(row.get("Price_Band")),
                "close_date": parse_close_date(row.get("End_Dt")),
                "lot_size": None,  # not present on this endpoint
                "raw": row,
            }
        )
    if not out:
        raise SourceBroken("BSE_LIVE had rows but zero equity IPOs after filter")
    return out


def _parse_times(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", "").strip())
    except ValueError:
        return None


def parse_subscription(payload: Any | None) -> dict[str, float | None]:
    """Extract QIB / NII / Retail / Total times from CATDEM table1."""
    empty = {"sub_qib": None, "sub_nii": None, "sub_retail": None, "sub_total": None}
    if payload is None:
        return empty
    rows = _catdem_rows(payload)
    if len(rows) <= 1:
        return empty

    sub_qib = sub_nii = sub_retail = sub_total = None
    for row in rows:
        cat = str(row.get("col2") or "").strip().lower()
        sr = str(row.get("SRNo") or "").strip()
        times = _parse_times(row.get("col5"))

        if cat == "total":
            sub_total = times
            continue
        # Top-level category rows only (SRNo is a single digit, not 1(a) / 2.1)
        if sr in ("1",) and "qualified institutional" in cat:
            sub_qib = times
        elif sr in ("2",) and "non institutional" in cat and "bid amount" not in cat:
            sub_nii = times
        elif sr in ("3",) and "retail" in cat:
            sub_retail = times

    return {
        "sub_qib": sub_qib,
        "sub_nii": sub_nii,
        "sub_retail": sub_retail,
        "sub_total": sub_total,
    }


def load_live_ipos() -> list[dict[str, Any]]:
    """Fetch live IPOs and attach subscription (may be None fields)."""
    live = parse_live(fetch_live())
    for ipo in live:
        cat = fetch_catdem(ipo["ipo_no"])
        ipo.update(parse_subscription(cat))
    return live
