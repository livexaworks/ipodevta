"""Build a personalized preview brief from cached IPO data (no Guru calls)."""

from __future__ import annotations

import logging
import re
from typing import Any

from bot import brief as brief_mod
from bot import config, score, state
from bot.brief import Brief
from bot.sources import ipoguru

log = logging.getLogger(__name__)


def _hhmm_from_ts(ts: str | None) -> str:
    if not ts:
        return "10:55"
    m = re.search(r"T(\d{2}):(\d{2})", str(ts))
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    return "10:55"


def _history_for(snapshots: list[dict[str, Any]], ipo_id: str) -> list[dict[str, Any]]:
    rows = [s for s in snapshots if s.get("ipo_id") == ipo_id]
    rows.sort(key=lambda r: (r.get("date") or "", r.get("ts") or ""))
    return rows


def _prev_close(history: list[dict[str, Any]], as_of: str) -> dict[str, Any] | None:
    prior = [h for h in history if h.get("date") and h["date"] < as_of]
    if not prior:
        return None
    last_date = prior[-1]["date"]
    same_day = [h for h in prior if h["date"] == last_date]
    return same_day[-1]


def _latest_unique_snapshots(limit: int) -> list[dict[str, Any]]:
    snaps = state.load_snapshots()
    by_id: dict[str, dict[str, Any]] = {}
    for row in snaps:
        iid = row.get("ipo_id")
        if not iid:
            continue
        cur = by_id.get(iid)
        key = (row.get("date") or "", row.get("ts") or "")
        if cur is None or key > (cur.get("date") or "", cur.get("ts") or ""):
            by_id[iid] = row
    ordered = sorted(
        by_id.values(),
        key=lambda r: (r.get("date") or "", r.get("ts") or ""),
        reverse=True,
    )
    return ordered[:limit]


def _latest_pool_from_snapshots() -> tuple[list[dict[str, Any]], str]:
    snaps = state.load_snapshots()
    by_id: dict[str, dict[str, Any]] = {}
    newest_ts = ""
    for row in snaps:
        iid = row.get("ipo_id")
        if not iid:
            continue
        key = (row.get("date") or "", row.get("ts") or "")
        cur = by_id.get(iid)
        if cur is None or key > (cur.get("date") or "", cur.get("ts") or ""):
            by_id[iid] = row
        if (row.get("ts") or "") > newest_ts:
            newest_ts = str(row.get("ts") or "")
    today = config.today_ist()
    openish = [r for r in by_id.values() if (r.get("close_date") or "9999") >= today]
    pool = openish or list(by_id.values())
    pool.sort(key=lambda r: (r.get("close_date") or "9999", r.get("name") or ""))
    return pool, _hhmm_from_ts(newest_ts)


def _live_fallback(limit: int = 50) -> tuple[list[dict[str, Any]], str]:
    try:
        from bot import preview_cache

        cached = preview_cache.load_cached_live_pool(limit)
        if cached:
            return cached, "10:55"
    except Exception as exc:  # noqa: BLE001
        log.warning("preview pool cache read failed: %s", exc)

    try:
        pool = ipoguru.fetch_open_ipos(allow_network=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("preview IPO Guru cache unavailable: %s", exc)
        return [], "10:55"

    pool = sorted(pool, key=lambda r: (r.get("close_date") or "9999", r.get("name") or ""))
    try:
        from bot import preview_cache

        preview_cache.save_live_pool(pool)
    except Exception as exc:  # noqa: BLE001
        log.warning("preview pool cache write failed: %s", exc)
    return pool[:limit], "10:55"


def build_brief_preview(
    prefs: dict[str, Any],
    *,
    live_pool: list[dict[str, Any]] | None = None,
) -> tuple[str, Brief | None]:
    """Brief from cached collect + snapshot history. Zero Guru network calls."""
    history = state.load_snapshots()
    if live_pool is not None:
        pool = live_pool
        hhmm = "10:55"
        source = "live"
    else:
        pool, hhmm = _latest_pool_from_snapshots()
        source = "processed"
        if not pool:
            pool, hhmm = _live_fallback()
            source = "live"

    if not pool:
        return source, None

    b = brief_mod.build_brief(
        pool,
        prefs,
        history,
        config.today_ist(),
        collect_hhmm=hhmm,
        as_of=True,
    )
    return source, b


def build_preview(
    prefs: dict[str, Any],
    *,
    limit: int = 5,
    live_pool: list[dict[str, Any]] | None = None,
) -> tuple[str, list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]]]:
    """Legacy scored-item preview (kept for unit tests)."""
    snaps = state.load_snapshots()
    recent = _latest_unique_snapshots(limit)

    if recent:
        items = []
        for row in recent:
            ipo_id = row.get("ipo_id") or ""
            hist = _history_for(snaps, ipo_id)
            as_of = row.get("date") or ""
            prev = _prev_close(hist, as_of)
            ipo_view = {**row, "history": hist}
            live = {
                "sub_total": row.get("sub_total"),
                "sub_qib": row.get("sub_qib"),
                "sub_nii": row.get("sub_nii"),
                "sub_retail": row.get("sub_retail"),
                "board": row.get("board"),
            }
            closing = bool(as_of and row.get("close_date") == as_of)
            verdict = score.evaluate(
                ipo_view, live, prev, hist, prefs=prefs, closing_today=closing
            )
            ok, reasons = verdict.as_legacy()
            items.append((ipo_view, ok, reasons, prev, live))
        return "processed", items

    if live_pool is None:
        live_pool, _hhmm = _live_fallback(limit)
    recent = live_pool[:limit]
    items = []
    for ipo in recent:
        live = {
            "sub_total": ipo.get("sub_total"),
            "sub_qib": ipo.get("sub_qib"),
            "sub_nii": ipo.get("sub_nii"),
            "sub_retail": ipo.get("sub_retail"),
            "board": ipo.get("board"),
        }
        closing = bool(ipo.get("close_date") == config.today_ist())
        verdict = score.evaluate(
            ipo, live, live, [], prefs=prefs, closing_today=closing
        )
        ok, reasons = verdict.as_legacy()
        items.append((ipo, ok, reasons, live, live))
    return "live", items


def load_live_preview_pool(limit: int = 5) -> list[dict[str, Any]]:
    pool, _hhmm = _live_fallback(max(limit, 5))
    return pool[:limit]
