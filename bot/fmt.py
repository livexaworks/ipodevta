"""Pure display formatters for Telegram HTML (no I/O)."""

from __future__ import annotations

import html
import math
from datetime import datetime
from typing import Any

# Tokens kept ALL CAPS after .title() normalisation (e.g. "FX Parts").
NAME_CASE_EXCEPTIONS = frozenset({"FX", "NSE", "BSE", "SME", "IPO", "QIB", "NII", "AI", "IT"})

_SUFFIXES = ("limited", "ltd", "llp")
_TREND = {"rising": "↑", "falling": "↓", "flat": "→"}
# Current renderer arrows (P0 goldens); brief uses TREND above.
_TREND_LEGACY = {"rising": "↗", "falling": "↘", "flat": "→"}


def esc(text: Any) -> str:
    if text is None:
        return "n/a"
    return html.escape(str(text), quote=False)


def strip_legal_suffix(name: str) -> str:
    parts = str(name).split()
    while parts and parts[-1].lower().rstrip(".") in _SUFFIXES:
        parts.pop()
    return " ".join(parts) if parts else str(name)


def display_name(name: str) -> str:
    """Title-case company names; strip Limited/Ltd; keep a small ALL-CAPS list."""
    short = strip_legal_suffix(str(name))
    words: list[str] = []
    for word in short.title().split():
        if word.upper() in NAME_CASE_EXCEPTIONS:
            words.append(word.upper())
        else:
            words.append(word)
    return " ".join(words) if words else short


def name_short(name: str, *, limit: int = 24) -> str:
    full = display_name(name)
    if len(full) <= limit:
        return full
    return full[: limit - 1] + "…"


def board_label(board: str | None) -> str:
    b = (board or "").upper()
    if b == "SME":
        return "SME"
    if b == "MAIN":
        return "Main"
    return board or "n/a"


def gmp_pct(val: Any) -> str | None:
    """Signed integer percent, e.g. +41% / -8% / 0%. None when missing."""
    if val is None:
        return None
    try:
        n = int(round(float(val)))
    except (TypeError, ValueError):
        return None
    return f"{n:+d}%" if n != 0 else "0%"


def sub(val: Any) -> str:
    """Subscription: <10 one decimal; >=10 integer; missing n/a."""
    if val is None:
        return "n/a"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(n):
        return "n/a"
    if abs(n) >= 10:
        return f"{int(round(n))}x"
    return f"{n:.1f}x"


def money(amount: Any, *, signed: bool = False) -> str | None:
    """₹ amount; uses L with up to 2 decimals at ₹1 lakh+."""
    if amount is None:
        return None
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n):
        return None
    sign = ""
    if signed:
        if n > 0:
            sign = "+"
        elif n < 0:
            sign = "-"
        n = abs(n)
    elif n < 0:
        sign = "-"
        n = abs(n)
    if n >= 100_000:
        lakhs = n / 100_000
        if lakhs == int(lakhs):
            body = f"₹{int(lakhs)}L"
        else:
            text = f"{lakhs:.2f}".rstrip("0").rstrip(".")
            body = f"₹{text}L"
        return f"{sign}{body}"
    return f"{sign}₹{n:,.0f}"


def lot_cost(price_high: Any, lot_size: Any) -> str | None:
    if price_high is None or lot_size is None:
        return None
    try:
        amount = float(price_high) * float(lot_size)
    except (TypeError, ValueError):
        return None
    return money(amount, signed=False)


def est_gain(gmp_rs: Any, lot_size: Any) -> str | None:
    if gmp_rs is None or lot_size is None:
        return None
    try:
        amount = float(gmp_rs) * float(lot_size)
    except (TypeError, ValueError):
        return None
    return money(amount, signed=True)


def trend(kind: str | None, *, legacy: bool = False) -> str:
    """Arrow for rising/falling/flat. Empty when unknown."""
    if not kind:
        return ""
    table = _TREND_LEGACY if legacy else _TREND
    return table.get(str(kind), "")


def date_heading(date_iso: str) -> str:
    """Current DM style: '5 Oct 2026'."""
    try:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
        return d.strftime("%d %b %Y").lstrip("0")
    except ValueError:
        return date_iso


def date_brief(date_iso: str) -> str:
    """Brief style: 'Wed 7 Oct' (no year). %-d is POSIX-only, so build manually."""
    try:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        return date_iso
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def date_weekday(date_iso: str) -> str:
    """Channel close day: weekday only."""
    try:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
        return d.strftime("%a")
    except ValueError:
        return date_iso


def fmt_num(val: Any, *, suffix: str = "", places: int | None = None) -> str:
    """Legacy number helper used by the current renderer."""
    if val is None:
        return "n/a"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "n/a"
    if places is not None:
        return f"{n:.{places}f}{suffix}"
    if n == int(n):
        return f"{int(n)}{suffix}"
    return f"{n:g}{suffix}"


def fmt_x(val: Any) -> str:
    """Legacy subscription: always two decimals."""
    if val is None:
        return "n/a"
    try:
        return f"{float(val):.2f}x"
    except (TypeError, ValueError):
        return "n/a"
