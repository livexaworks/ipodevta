"""User filters: board, GMP% bar per board, minimum total subscription.

Mirrors passesFilter() in workers/telegram/worker.js; keep both in sync.
"""

from __future__ import annotations

from typing import Any

from bot import config

BOARDS = ("main", "sme", "both")


def _float(val: Any, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def normalize(prefs: dict[str, Any] | None) -> dict[str, Any]:
    """Canonical prefs. Reads the pre-2026-10 keys (min_gmp_pct, include_sme) once."""
    p = prefs or {}
    board = str(p.get("board") or "").lower()
    if board not in BOARDS:
        board = "both" if p.get("include_sme") else config.DEFAULT_BOARD
    legacy_gmp = p.get("min_gmp_pct")
    main = _float(p.get("min_gmp_main", legacy_gmp), config.MIN_GMP_MAIN)
    sme_default = legacy_gmp if "board" not in p and "min_gmp_sme" not in p else None
    sme = _float(p.get("min_gmp_sme", sme_default), config.MIN_GMP_SME)
    sub = _float(p.get("min_total_sub"), config.MIN_TOTAL_SUB)
    return {"board": board, "min_gmp_main": main, "min_gmp_sme": sme, "min_total_sub": sub}


def passes(ipo: dict[str, Any], prefs: dict[str, Any]) -> bool:
    p = normalize(prefs)
    board = ipo.get("board")
    if board == "SME":
        if p["board"] == "main":
            return False
        bar = p["min_gmp_sme"]
    elif board == "MAIN":
        if p["board"] == "sme":
            return False
        bar = p["min_gmp_main"]
    else:
        return False

    gmp_pct, sub_total = ipo.get("gmp_pct"), ipo.get("sub_total")
    if gmp_pct is None or sub_total is None:
        return False
    return float(gmp_pct) >= bar and float(sub_total) >= p["min_total_sub"]
