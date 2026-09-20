"""Message formatting for channel feed and personalized DMs."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from bot import keyboards, score as score_mod

DISCLAIMER = (
    "Grey-market premium is unofficial and can move quickly.\n"
    "This is information only - not investment advice. Read the RHP.\n"
    "Sources: BSE · IPO Watch · IPO Central · Investorgain"
)

TREND_ARROW = {"rising": "↗ rising", "falling": "↘ falling", "flat": "→ flat"}


def esc(text: Any) -> str:
    if text is None:
        return "n/a"
    return html.escape(str(text), quote=False)


def _fmt_num(val: Any, *, suffix: str = "", places: int | None = None) -> str:
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


def _fmt_x(val: Any) -> str:
    if val is None:
        return "n/a"
    try:
        return f"{float(val):.2f}x"
    except (TypeError, ValueError):
        return "n/a"


def _short_name(name: str) -> str:
    parts = str(name).split()
    while parts and parts[-1].lower().rstrip(".") in ("limited", "ltd", "llp"):
        parts.pop()
    return " ".join(parts) if parts else name


def _date_heading(date_iso: str) -> str:
    try:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
        return d.strftime("%d %b %Y").lstrip("0")
    except ValueError:
        return date_iso


def _lot_line(ipo: dict[str, Any]) -> str | None:
    lot = ipo.get("lot_size")
    price = ipo.get("price_high")
    if lot is None:
        return None
    if price is not None:
        try:
            amount = int(lot) * float(price)
            return f"Lot {int(lot)} shares ≈ ₹{amount:,.0f}"
        except (TypeError, ValueError):
            pass
    return f"Lot {lot} shares"


def _sub_block(label: str, snap: dict[str, Any] | None) -> str:
    if snap is None:
        return f"{label}: n/a"
    return (
        f"{label}:\n"
        f"  QIB {_fmt_x(snap.get('sub_qib'))} · NII {_fmt_x(snap.get('sub_nii'))} · "
        f"Retail {_fmt_x(snap.get('sub_retail'))} · Total {_fmt_x(snap.get('sub_total'))}"
    )


def prefs_summary(prefs: dict[str, Any]) -> str:
    board = "MAIN + SME" if prefs.get("include_sme") else "MAIN only"
    return (
        f"Min GMP: {_fmt_num(prefs.get('min_gmp_pct'), suffix='%')}\n"
        f"Min subscription: {_fmt_num(prefs.get('min_total_sub'), suffix='x')}\n"
        f"Board: {board}"
    )


def welcome_text(prefs: dict[str, Any]) -> str:
    channel = keyboards.channel_url()
    return (
        "<b>IPO Devta</b>\n"
        "Your IPO fill assistant.\n\n"
        "On closing days you receive a clear 👍 / 👎 view based on "
        "<b>your</b> filters - GMP, subscription, and board - so you know "
        "what to consider filing.\n\n"
        "Use the buttons below. No typing required.\n\n"
        f"<b>Your filters</b>\n{html.escape(prefs_summary(prefs), quote=False)}\n\n"
        "Prefer a quieter feed? Join the public channel for the daily closing "
        f"list without personal filters:\n{esc(channel)}\n\n"
        "No selling. No promotions. Just timely IPO fill reminders."
    )


def help_text() -> str:
    channel = keyboards.channel_url()
    return (
        "<b>How IPO Devta works</b>\n\n"
        "• <b>Preview GMP</b> - last five processed issues, scored with your filters "
        "(or a live look at open issues if history is still building).\n"
        "• <b>Settings</b> - tap to set min GMP %, min subscription, and board.\n"
        "• <b>Channel</b> - public closing-day feed if you prefer not to use DMs.\n\n"
        "Weekday mornings: when issues close that day, you get a personalized DM.\n"
        "Weekday evenings: we record the book for the next morning’s decision.\n\n"
        f"Channel: {esc(channel)}\n\n"
        f"{DISCLAIMER}"
    )


def settings_text(prefs: dict[str, Any]) -> str:
    return (
        "<b>Your filters</b>\n\n"
        f"{html.escape(prefs_summary(prefs), quote=False)}\n\n"
        "Tap a button to update. Your next Preview and closing-day DM "
        "use these values immediately."
    )


def render_preview(
    prefs: dict[str, Any],
    source: str,
    items: list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]],
) -> str:
    if source == "live":
        heading = "Preview · open issues (live)"
        note = (
            "Snapshot history is still building - showing live open issues "
            "scored with your filters."
        )
    else:
        heading = "Preview · last 5 processed"
        note = "Scored with your current filters - the same logic used on closing-day DMs."

    if not items:
        return (
            f"<b>{esc(heading)}</b>\n\n"
            "Nothing to show yet. Check again after the next market scan.\n\n"
            f"<b>Your filters</b>\n{html.escape(prefs_summary(prefs), quote=False)}"
        )

    parts = [
        f"<b>{esc(heading)}</b>",
        esc(note),
        "",
        "<b>Your filters</b>",
        html.escape(prefs_summary(prefs), quote=False),
        "",
    ]
    ups = [x for x in items if x[1]]
    downs = [x for x in items if not x[1]]
    for ipo, _ok, _reasons, prev, live in ups:
        parts.append(render_thumb_up(ipo, prev=prev, live=live))
        parts.append("")
    for ipo, _ok, reasons, _prev, _live in downs:
        parts.append(render_thumb_down(ipo, reasons))
    if downs:
        parts.append("")
    parts.append(DISCLAIMER)
    return "\n".join(parts).strip()


def render_thumb_up(
    ipo: dict[str, Any], *, prev: dict[str, Any] | None, live: dict[str, Any] | None
) -> str:
    name = _short_name(ipo.get("name") or ipo.get("ipo_id") or "?")
    trend = score_mod.gmp_trend(ipo.get("history") or [])
    arrow = TREND_ARROW.get(trend, trend)
    gmp = ipo.get("gmp")
    price = ipo.get("price_high")
    gmp_pct = ipo.get("gmp_pct")
    lines = [
        f"👍 <b>{esc(name)}</b>",
        (
            f"GMP ₹{_fmt_num(gmp)} on ₹{_fmt_num(price)} = {_fmt_num(gmp_pct, suffix='%')} "
            f"({arrow})"
        ),
        (
            f"{_fmt_num(ipo.get('n_sources'))} sources · "
            f"{_fmt_num(ipo.get('spread_pct'), suffix='%')} spread · "
            f"{esc(ipo.get('confidence') or 'n/a')} confidence"
        ),
        _sub_block("Subscription (prior close)", prev),
        f"Live book: Total {_fmt_x((live or ipo).get('sub_total'))}",
    ]
    lot = _lot_line(ipo)
    if lot:
        lines.append(lot)
    close = ipo.get("close_date")
    if close:
        lines.append(f"Closes: {esc(_date_heading(str(close)))}")
    return "\n".join(lines)


def render_thumb_down(ipo: dict[str, Any], reasons: list[str]) -> str:
    name = _short_name(ipo.get("name") or ipo.get("ipo_id") or "?")
    reason = reasons[0] if reasons else "did not pass filters"
    gmp_pct = ipo.get("gmp_pct")
    extra = f" · GMP {_fmt_num(gmp_pct, suffix='%')}" if gmp_pct is not None else ""
    return f"👎 {esc(name)}{extra} · {esc(reason)}"


def render_dm(
    date_iso: str,
    items: list[
        tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]
    ],
) -> str:
    """items: (ipo, ok, reasons, prev, live)"""
    ups = [x for x in items if x[1]]
    downs = [x for x in items if not x[1]]
    parts = [f"📋 <b>Closing today · {esc(_date_heading(date_iso))}</b>", ""]
    for ipo, _ok, _reasons, prev, live in ups:
        parts.append(render_thumb_up(ipo, prev=prev, live=live))
        parts.append("")
    for ipo, _ok, reasons, _prev, _live in downs:
        parts.append(render_thumb_down(ipo, reasons))
    if downs:
        parts.append("")
    parts.append(DISCLAIMER)
    return "\n".join(parts).strip()


def render_channel(date_iso: str, ipos: list[dict[str, Any]]) -> str:
    """Unfiltered daily GMP feed - all closing IPOs, no personal gates."""
    parts = [f"📋 <b>Closing today · {esc(_date_heading(date_iso))}</b>", ""]
    for ipo in ipos:
        name = _short_name(ipo.get("name") or "?")
        board = ipo.get("board") or "n/a"
        parts.append(f"<b>{esc(name)}</b> · {esc(board)}")
        parts.append(
            f"GMP ₹{_fmt_num(ipo.get('gmp'))} on ₹{_fmt_num(ipo.get('price_high'))} "
            f"= {_fmt_num(ipo.get('gmp_pct'), suffix='%')} "
            f"({esc(ipo.get('confidence') or 'n/a')} · "
            f"{_fmt_num(ipo.get('n_sources'))} sources)"
        )
        parts.append(
            f"Sub live: QIB {_fmt_x(ipo.get('sub_qib'))} · NII {_fmt_x(ipo.get('sub_nii'))} · "
            f"Retail {_fmt_x(ipo.get('sub_retail'))} · Total {_fmt_x(ipo.get('sub_total'))}"
        )
        parts.append("")
    parts.append(DISCLAIMER)
    return "\n".join(parts).strip()
