"""Pure display formatters for Telegram HTML (no I/O)."""

from __future__ import annotations

import html
import math
from datetime import datetime
from typing import Any

# Tokens kept ALL CAPS after .title() normalisation (e.g. "FX Parts").
NAME_CASE_EXCEPTIONS = frozenset({"FX", "NSE", "BSE", "SME", "IPO", "QIB", "NII", "AI", "IT"})
_SUFFIXES = ("limited", "ltd", "llp")


def esc(text: Any) -> str:
    return html.escape("" if text is None else str(text), quote=False)


def _num(val: Any) -> float | None:
    if val is None:
        return None
    try:
        n = float(val)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def display_name(name: str) -> str:
    """Title-case company names; strip Limited/Ltd; keep a small ALL-CAPS list."""
    parts = str(name).split()
    while parts and parts[-1].lower().rstrip(".") in _SUFFIXES:
        parts.pop()
    short = " ".join(parts) if parts else str(name)
    words = [
        w.upper() if w.upper() in NAME_CASE_EXCEPTIONS else w
        for w in short.title().split()
    ]
    return " ".join(words) if words else short


def board_label(board: str | None) -> str:
    return "SME" if (board or "").upper() == "SME" else "Mainboard"


def rupees(val: Any) -> str | None:
    """₹220 / ₹1,250.5 — whole numbers without decimals."""
    n = _num(val)
    if n is None:
        return None
    sign = "-" if n < 0 else ""
    n = abs(n)
    body = f"{n:,.0f}" if n == int(n) else f"{n:,.2f}".rstrip("0").rstrip(".")
    return f"{sign}₹{body}"


def pct(val: Any) -> str | None:
    """Signed one-decimal percent: +9.1% / -2.5% / 0%."""
    n = _num(val)
    if n is None:
        return None
    n = round(n, 1)
    if n == 0:
        return "0%"
    return f"{n:+.1f}".removesuffix(".0") + "%"


def sub(val: Any) -> str | None:
    """Subscription times: under 10 one decimal, otherwise whole."""
    n = _num(val)
    if n is None:
        return None
    if abs(n) >= 10:
        return f"{int(round(n))}x"
    return f"{n:.1f}".removesuffix(".0") + "x"


def date_short(date_iso: str | None) -> str | None:
    """'30 Sep'."""
    if not date_iso:
        return None
    try:
        d = datetime.strptime(str(date_iso)[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return f"{d.day} {d.strftime('%b')}"


def date_long(date_iso: str) -> str:
    """'Thu 8 Oct'."""
    d = datetime.strptime(date_iso[:10], "%Y-%m-%d")
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def time_12h(hhmm: str) -> str:
    """'14:30' -> '2:30 PM'."""
    h, m = (int(x) for x in hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    return f"{(h % 12) or 12}:{m:02d} {suffix}"
