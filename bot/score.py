"""Gates and verdict - previous-day subscription, never live 11:00 QIB."""

from __future__ import annotations

import statistics
from typing import Any

from bot import config

MIN_GMP_PCT = config.MIN_GMP_PCT
MIN_TOTAL_SUB = config.MIN_TOTAL_SUB
MIN_CONFIDENCE = config.MIN_CONFIDENCE
INCLUDE_SME = config.INCLUDE_SME
BLOCK_FALLING_GMP = config.BLOCK_FALLING_GMP

_CONF = config.CONFIDENCE_RANK


def gmp_trend(history: list[dict[str, Any]]) -> str:
    vals = [h["gmp_pct"] for h in history if h.get("gmp_pct") is not None]
    if len(vals) < 4:
        return "flat"
    mid = len(vals) // 2
    a, b = statistics.median(vals[:mid]), statistics.median(vals[mid:])
    if not a:
        return "flat"
    d = (b - a) / a * 100
    return "rising" if d > 8 else "falling" if d < -12 else "flat"


def evaluate(
    ipo: dict[str, Any],
    live: dict[str, Any] | None,
    prev_close: dict[str, Any] | None,
    history: list[dict[str, Any]],
    *,
    prefs: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """
    Return (thumbs_up, reasons).
    Gates use prev_close subscription and consolidated GMP on `ipo`.
    `live` is context only - never gated on.
    """
    p = prefs or {}
    min_gmp = float(p.get("min_gmp_pct", MIN_GMP_PCT))
    min_sub = float(p.get("min_total_sub", MIN_TOTAL_SUB))
    include_sme = bool(p.get("include_sme", INCLUDE_SME))
    min_conf = str(p.get("min_confidence", MIN_CONFIDENCE))
    block_falling = bool(p.get("block_falling_gmp", BLOCK_FALLING_GMP))

    reasons: list[str] = []
    board = ipo.get("board") or (live or {}).get("board")
    gmp_pct = ipo.get("gmp_pct")
    confidence = ipo.get("confidence") or "low"
    trend = gmp_trend(history)

    if board != "MAIN" and not (include_sme and board == "SME"):
        if board == "SME":
            reasons.append("SME issue, excluded")
        else:
            reasons.append(f"board {board or 'n/a'} excluded")

    if gmp_pct is None:
        reasons.append("GMP n/a")
    elif gmp_pct < min_gmp:
        reasons.append(f"GMP {gmp_pct}% below {min_gmp:g}% bar")

    if prev_close is None:
        reasons.append("insufficient history")
    else:
        sub_total = prev_close.get("sub_total")
        if sub_total is None:
            reasons.append("prior subscription n/a")
        elif sub_total < min_sub:
            reasons.append(f"prior total sub {sub_total}x below {min_sub:g}x")

    if _CONF.get(confidence, 0) < _CONF.get(min_conf, 1):
        reasons.append(f"GMP confidence only {confidence}")

    if block_falling and trend == "falling":
        reasons.append("GMP trend falling")

    # live is intentionally unused for gates
    _ = live

    return (len(reasons) == 0, reasons)
