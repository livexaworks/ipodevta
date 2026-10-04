"""Gates and verdict - previous-day subscription, never live 11:00 QIB."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Literal

from bot import config, copy
from bot.prefs import board_mode, gmp_for_board

MIN_GMP_PCT = config.MIN_GMP_PCT
MIN_TOTAL_SUB = config.MIN_TOTAL_SUB
MIN_CONFIDENCE = config.MIN_CONFIDENCE
INCLUDE_SME = config.INCLUDE_SME
BLOCK_FALLING_GMP = config.BLOCK_FALLING_GMP

_CONF = config.CONFIDENCE_RANK

State = Literal["FIT", "SKIP", "WAIT", "CHECK", "HIDDEN"]

# Soft / missing-data codes → WAIT or CHECK when nothing else failed.
_MISSING_CODES = frozenset({"GMP_MISSING", "NO_PRIOR_SUB", "SUB_MISSING"})


@dataclass(frozen=True)
class Verdict:
    state: State
    reason_code: str | None = None
    actual: Any = None
    required: Any = None
    # Extra template fields (e.g. GMP_FALLING from/to, BOARD_EXCLUDED board)
    extras: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.state == "FIT"

    def reason_text(self) -> str | None:
        if not self.reason_code:
            return None
        kwargs: dict[str, Any] = {}
        if self.actual is not None:
            kwargs["actual"] = self.actual
        if self.required is not None:
            kwargs["required"] = self.required
        if self.extras:
            kwargs.update(self.extras)
        # from/to collide with Python builtins in format — stored as extras
        return copy.t(f"reasons.{self.reason_code}", **kwargs)

    def as_legacy(self) -> tuple[bool, list[str]]:
        """Compat for the current renderer: (thumbs_up, reason strings)."""
        if self.state == "FIT":
            return True, []
        text = self.reason_text()
        return False, [text] if text else []


def gmp_trend(history: list[dict[str, Any]]) -> str:
    kind, _a, _b = gmp_trend_detail(history)
    return kind


def gmp_trend_detail(
    history: list[dict[str, Any]],
) -> tuple[str, float | None, float | None]:
    vals = [h["gmp_pct"] for h in history if h.get("gmp_pct") is not None]
    if len(vals) < 4:
        return "flat", None, None
    mid = len(vals) // 2
    a, b = statistics.median(vals[:mid]), statistics.median(vals[mid:])
    if not a:
        return "flat", float(a), float(b)
    d = (b - a) / a * 100
    kind = "rising" if d > 8 else "falling" if d < -12 else "flat"
    return kind, float(a), float(b)


def _num_display(val: Any) -> str:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return str(val)
    if n == int(n):
        return str(int(n))
    return f"{n:g}"


def evaluate(
    ipo: dict[str, Any],
    live: dict[str, Any] | None,
    prev_close: dict[str, Any] | None,
    history: list[dict[str, Any]],
    *,
    prefs: dict[str, Any] | None = None,
    closing_today: bool = False,
) -> Verdict:
    """
    Structured verdict. Gate order and thresholds are unchanged.

    Gates use prev_close subscription and consolidated GMP on `ipo`.
    `live` is context only - never gated on.
    Missing GMP / prior-day sub map to WAIT or CHECK only when nothing else failed.
    """
    p = prefs or {}
    mode = board_mode(p)
    min_sub = float(p.get("min_total_sub", MIN_TOTAL_SUB))
    min_conf = str(p.get("min_confidence", MIN_CONFIDENCE))
    block_falling = bool(p.get("block_falling_gmp", BLOCK_FALLING_GMP))

    board = ipo.get("board") or (live or {}).get("board")
    gmp_pct = ipo.get("gmp_pct")
    confidence = ipo.get("confidence") or "low"
    trend, trend_from, trend_to = gmp_trend_detail(history)
    min_gmp = gmp_for_board(p, board if board in ("MAIN", "SME") else "MAIN")

    # live is intentionally unused for gates
    _ = live

    # 1. Board exclusion → HIDDEN (never SKIP by name in the brief)
    if board == "SME" and mode == "main":
        return Verdict(state="HIDDEN", reason_code="BOARD_SME_EXCLUDED")
    if board == "MAIN" and mode == "sme":
        return Verdict(state="HIDDEN", reason_code="BOARD_MAIN_EXCLUDED")
    if board not in ("MAIN", "SME"):
        return Verdict(
            state="HIDDEN",
            reason_code="BOARD_EXCLUDED",
            extras={"board": board or "n/a"},
        )

    # Walk gates in the existing order; keep the first hard and first soft hit.
    hard: Verdict | None = None
    soft: Verdict | None = None

    def _hard(code: str, *, actual: Any = None, required: Any = None, extras: dict | None = None) -> None:
        nonlocal hard
        if hard is None:
            hard = Verdict(
                state="SKIP",
                reason_code=code,
                actual=actual,
                required=required,
                extras=extras,
            )

    def _soft(code: str, *, actual: Any = None, required: Any = None) -> None:
        nonlocal soft
        if soft is None:
            soft = Verdict(
                state="WAIT",  # placeholder; remapped below
                reason_code=code,
                actual=actual,
                required=required,
            )

    # 2. GMP
    if gmp_pct is None:
        _soft("GMP_MISSING")
    elif gmp_pct < min_gmp:
        _hard(
            "GMP_BELOW",
            actual=_num_display(gmp_pct),
            required=_num_display(min_gmp),
        )

    # 3. Prior-day subscription
    if prev_close is None:
        _soft("NO_PRIOR_SUB")
    else:
        sub_total = prev_close.get("sub_total")
        if sub_total is None:
            _soft("SUB_MISSING")
        elif sub_total < min_sub:
            _hard(
                "SUB_BELOW",
                actual=_num_display(sub_total),
                required=_num_display(min_sub),
            )

    # 4. Confidence
    if _CONF.get(confidence, 0) < _CONF.get(min_conf, 1):
        _hard("LOW_CONFIDENCE")

    # 5. Falling GMP (optional)
    if block_falling and trend == "falling":
        extras = None
        if trend_from is not None and trend_to is not None:
            extras = {
                "from": _num_display(trend_from),
                "to": _num_display(trend_to),
            }
        _hard("GMP_FALLING", extras=extras)

    if hard is not None:
        return hard

    if soft is not None:
        assert soft.reason_code in _MISSING_CODES
        state: State = "CHECK" if closing_today else "WAIT"
        return Verdict(
            state=state,
            reason_code=soft.reason_code,
            actual=soft.actual,
            required=soft.required,
            extras=soft.extras,
        )

    return Verdict(state="FIT")
