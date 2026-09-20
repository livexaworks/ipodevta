"""Three GMP scrapers behind one interface + consolidate()."""

from __future__ import annotations

import logging
import re
import statistics
import time
from io import StringIO
from typing import Any, Callable

import pandas as pd
import requests

from bot import config

log = logging.getLogger(__name__)


class SourceBroken(RuntimeError):
    def __init__(self, source: str, reason: str):
        self.source = source
        self.reason = reason
        super().__init__(f"{source}: {reason}")


def norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def pick_col(cols: list[Any], *candidates: str) -> Any | None:
    for cand in candidates:
        c = norm(cand)
        for col in cols:
            if c in norm(col):
                return col
    return None


def _parse_number(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    text = str(val).strip()
    if not text or text.lower() in ("nan", "na", "n/a", "-", "—", ""):
        return None
    # GMP often like "+88", "88", "₹88", "88-90"
    text = text.replace("₹", "").replace(",", "").replace("%", "")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _promote_header_row(df: pd.DataFrame) -> pd.DataFrame:
    """When pandas uses 0,1,2… columns, first data row is often the real header."""
    cols = [str(c) for c in df.columns]
    if not cols:
        return df
    numeric_like = all(norm(c).isdigit() or norm(c).startswith("unnamed") for c in cols)
    if not numeric_like or df.empty:
        return df
    header = [str(x).strip() for x in list(df.iloc[0])]
    out = df.iloc[1:].copy()
    out.columns = header
    out.reset_index(drop=True, inplace=True)
    return out


def _all_tables(html: str) -> list[pd.DataFrame]:
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError:
        tables = []
    if not tables:
        try:
            tables = pd.read_html(StringIO(html), flavor="html5lib")
        except ValueError:
            tables = []
    return [_promote_header_row(t) for t in tables]


def _largest_table(html: str) -> pd.DataFrame:
    tables = _all_tables(html)
    if not tables:
        raise ValueError("no HTML tables found")
    return max(tables, key=lambda t: t.shape[0] * max(t.shape[1], 1))


def _rows_from_html(html: str, source: str) -> list[dict[str, Any]]:
    """Parse every table on the page and merge rows (sites often split MAIN/SME)."""
    tables = _all_tables(html)
    if not tables:
        raise ValueError("no HTML tables found")
    merged: list[dict[str, Any]] = []
    errors: list[str] = []
    for df in tables:
        try:
            merged.extend(_rows_from_df(df, source))
        except ValueError as exc:
            errors.append(str(exc))
    if not merged:
        raise ValueError("; ".join(errors) if errors else "no parseable GMP tables")
    # de-dupe by raw_name keeping first
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in merged:
        key = row["raw_name"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _rows_from_df(df: pd.DataFrame, source: str) -> list[dict[str, Any]]:
    cols = [str(c) for c in df.columns]
    name_col = pick_col(cols, "ipo", "company", "name")
    gmp_col = pick_col(cols, "gmp", "premium")
    # Prefer issue/price band over estimated listing price
    price_col = pick_col(cols, "price band", "issue price", "price", "band", "issueprice")
    if name_col is None or gmp_col is None:
        raise ValueError(f"missing name/gmp columns in {cols}")

    rows: list[dict[str, Any]] = []
    for _, series in df.iterrows():
        raw_name = series.get(name_col)
        if raw_name is None or (isinstance(raw_name, float) and pd.isna(raw_name)):
            continue
        name = str(raw_name).strip()
        if not name or name.lower() in ("nan", "ipo", "company", "name"):
            continue
        gmp = _parse_number(series.get(gmp_col))
        price_hint = _parse_number(series.get(price_col)) if price_col else None
        rows.append(
            {
                "source": source,
                "raw_name": name,
                "gmp": gmp,
                "price_hint": price_hint,
            }
        )
    return rows


def _fetch_html(url: str) -> str:
    headers = {"User-Agent": config.USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def _rows_from_ipocentral_ticker(html: str) -> list[dict[str, Any]]:
    """
    IPO Central's list page now ships empty <table> shells; live GMP sits in the
    homepage-style ticker markup (name + numeric GMP). Fallback when read_html
    finds nothing usable.
    """
    pairs = re.findall(
        r'ipogmp__name">\s*([^<]+?)\s*</span>\s*'
        r'<span class="ipogmp__gmp[^"]*"[^>]*>\s*'
        r'<span class="ipogmp__num">\s*([+\-]?\d+(?:\.\d+)?)\s*</span>',
        html,
    )
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name, gmp_s in pairs:
        name = name.strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source": "ipocentral",
                "raw_name": name,
                "gmp": float(gmp_s),
                "price_hint": None,
            }
        )
    return rows


def scrape_investorgain() -> list[dict[str, Any]]:
    html = _fetch_html(config.GMP_URLS["investorgain"])
    return _rows_from_html(html, "investorgain")


def scrape_ipowatch() -> list[dict[str, Any]]:
    html = _fetch_html(config.GMP_URLS["ipowatch"])
    return _rows_from_html(html, "ipowatch")


def scrape_ipocentral() -> list[dict[str, Any]]:
    html = _fetch_html(config.GMP_URLS["ipocentral"])
    try:
        return _rows_from_html(html, "ipocentral")
    except ValueError:
        rows = _rows_from_ipocentral_ticker(html)
        if not rows:
            raise
        return rows


SCRAPERS: dict[str, Callable[[], list[dict[str, Any]]]] = {
    "investorgain": scrape_investorgain,
    "ipowatch": scrape_ipowatch,
    "ipocentral": scrape_ipocentral,
}


def fetch_all_gmp(*, sleep_s: float = 2.5) -> tuple[list[dict[str, Any]], list[SourceBroken]]:
    """
    Run all scrapers. Per-source failures collected; zero rows → SourceBroken.
    Returns (quotes, errors). Caller decides whether errors are fatal.
    """
    quotes: list[dict[str, Any]] = []
    errors: list[SourceBroken] = []
    for i, (name, fn) in enumerate(SCRAPERS.items()):
        if i:
            time.sleep(sleep_s)
        try:
            rows = fn()
            if not rows:
                raise SourceBroken(name, "zero parsed rows")
            quotes.extend(rows)
            log.info("GMP %s: %d rows", name, len(rows))
        except SourceBroken as exc:
            errors.append(exc)
            log.error("%s", exc)
        except Exception as exc:  # noqa: BLE001
            err = SourceBroken(name, str(exc))
            errors.append(err)
            log.error("%s", err)
    return quotes, errors


def parse_html_fixture(html: str, source: str) -> list[dict[str, Any]]:
    """Used by tests against saved HTML."""
    rows = _rows_from_html(html, source)
    if not rows:
        raise SourceBroken(source, "zero parsed rows")
    return rows


def consolidate(quotes: list[dict[str, Any]], issue_price: float | None) -> dict[str, Any] | None:
    vals = [q["gmp"] for q in quotes if q.get("gmp") is not None]
    if not vals or not issue_price:
        return None
    med = statistics.median(vals)
    spread = (max(vals) - min(vals)) / med * 100 if med else 0.0
    n = len(vals)
    if n >= 3 and spread < 20:
        confidence = "high"
    elif n >= 2 and spread < 40:
        confidence = "medium"
    else:
        confidence = "low"
    return {
        "gmp": med,
        "gmp_pct": round(med / issue_price * 100, 2),
        "n_sources": n,
        "spread_pct": round(spread, 1),
        "confidence": confidence,
    }
