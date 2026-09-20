"""Build a personalized preview of recent / live IPOs for testing filters."""

from __future__ import annotations

import logging
from typing import Any

from bot import match, score, state
from bot.sources import bse, gmp

log = logging.getLogger(__name__)


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


def _live_fallback(limit: int) -> list[dict[str, Any]]:
    """When no snapshots exist yet, score currently open issues."""
    try:
        live_ipos = bse.load_live_ipos()
    except Exception as exc:  # noqa: BLE001
        log.warning("preview live BSE failed: %s", exc)
        return []
    quotes, errors = gmp.fetch_all_gmp()
    if errors:
        log.warning("preview GMP partial: %s", errors)
    enriched, _ = match.join_gmp_to_ipos(live_ipos, quotes)
    for ipo in enriched:
        cons = gmp.consolidate(ipo.get("gmp_quotes") or [], ipo.get("price_high"))
        if cons:
            ipo.update(cons)
    # Prefer issues closing soonest
    enriched.sort(key=lambda r: (r.get("close_date") or "9999", r.get("name") or ""))
    return enriched[:limit]


def build_preview(
    prefs: dict[str, Any],
    *,
    limit: int = 5,
    live_pool: list[dict[str, Any]] | None = None,
) -> tuple[str, list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]]]:
    """
    Return (source_label, items) where items match render.render_dm shape:
    (ipo, ok, reasons, prev, live).

    Pass live_pool to reuse one live fetch across many Preview taps in a drain.
    """
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
            ok, reasons = score.evaluate(ipo_view, live, prev, hist, prefs=prefs)
            items.append((ipo_view, ok, reasons, prev, live))
        return "processed", items

    if live_pool is None:
        live_pool = _live_fallback(limit)
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
        ok, reasons = score.evaluate(ipo, live, live, [], prefs=prefs)
        items.append((ipo, ok, reasons, live, live))
    return "live", items


def load_live_preview_pool(limit: int = 5) -> list[dict[str, Any]]:
    """Fetch once per drain — shared across many Preview button taps."""
    return _live_fallback(limit)
