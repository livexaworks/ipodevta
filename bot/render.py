"""Message formatting for channel feed and personalized DMs."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from bot import keyboards, score as score_mod

DISCLAIMER = (
    "<i>Grey-market premium is unofficial and can move quickly.\n"
    "Information only - not investment advice. Read the RHP.</i>"
)

RULE = "────────────"
TREND_ARROW = {"rising": "↗", "falling": "↘", "flat": "→"}


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
            return f"Lot {int(lot)} · ≈ ₹{amount:,.0f}"
        except (TypeError, ValueError):
            pass
    return f"Lot {lot}"


def prefs_summary(prefs: dict[str, Any]) -> str:
    board = "MAIN + SME" if prefs.get("include_sme") else "MAIN only"
    return (
        f"GMP min     {_fmt_num(prefs.get('min_gmp_pct'), suffix='%')}\n"
        f"Sub min     {_fmt_num(prefs.get('min_total_sub'), suffix='x')}\n"
        f"Board       {board}"
    )


def prefs_block(prefs: dict[str, Any]) -> str:
    return f"<b>Your filters</b>\n<code>{html.escape(prefs_summary(prefs), quote=False)}</code>"


def welcome_text(prefs: dict[str, Any]) -> str:
    channel = keyboards.channel_url()
    return "\n".join(
        [
            "<b>IPO Devta</b>",
            "<i>Your IPO fill assistant</i>",
            "",
            "On closing days you get a clear 👍 / 👎 view from "
            "<b>your</b> filters - so you know what to consider filing.",
            "",
            prefs_block(prefs),
            "",
            RULE,
            "",
            "Use the buttons below - no typing needed.",
            "",
            f'Prefer a shared feed? <a href="{channel}">Join the channel</a>',
            "",
            "<i>No selling. No promotions. Just fill reminders.</i>",
        ]
    )


def help_text() -> str:
    channel = keyboards.channel_url()
    return "\n".join(
        [
            "<b>How it works</b>",
            "",
            "<b>Preview GMP</b>",
            "Last five scored issues with your filters.",
            "",
            "<b>Settings</b>",
            "Tap to set GMP %, subscription, and board.",
            "",
            "<b>Channel</b>",
            "Public closing-day feed without personal filters.",
            "",
            RULE,
            "",
            "Weekday morning - personalized DM when issues close",
            "Weekday evening - book recorded for next day",
            "",
            f'<a href="{channel}">Open channel</a>',
            "",
            DISCLAIMER,
        ]
    )


def settings_text(prefs: dict[str, Any]) -> str:
    return "\n".join(
        [
            "<b>Settings</b>",
            "",
            prefs_block(prefs),
            "",
            "Tap a value below to update.",
            "Changes apply to Preview and closing-day DMs right away.",
        ]
    )


def render_preview(
    prefs: dict[str, Any],
    source: str,
    items: list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]],
) -> str:
    if source == "live":
        heading = "Preview · live open issues"
        note = "History is still building - scoring open issues with your filters."
    else:
        heading = "Preview · last 5 processed"
        note = "Same scoring logic as your closing-day DM."

    if not items:
        return "\n".join(
            [
                f"<b>{esc(heading)}</b>",
                "",
                "Nothing to show yet.",
                "Check again after the next market scan.",
                "",
                prefs_block(prefs),
            ]
        )

    ups = [x for x in items if x[1]]
    downs = [x for x in items if not x[1]]
    parts = [
        f"<b>{esc(heading)}</b>",
        f"<i>{esc(note)}</i>",
        "",
        prefs_block(prefs),
        "",
        RULE,
    ]
    if ups:
        parts.extend(["", f"<b>Consider filing · {len(ups)}</b>", ""])
        for ipo, _ok, _reasons, prev, live in ups:
            parts.append(render_thumb_up(ipo, prev=prev, live=live))
            parts.append("")
    if downs:
        parts.extend([f"<b>Skip · {len(downs)}</b>", ""])
        for ipo, _ok, reasons, _prev, _live in downs:
            parts.append(render_thumb_down(ipo, reasons))
        parts.append("")
    parts.append(DISCLAIMER)
    return "\n".join(parts).strip()


def render_thumb_up(
    ipo: dict[str, Any], *, prev: dict[str, Any] | None, live: dict[str, Any] | None
) -> str:
    name = _short_name(ipo.get("name") or ipo.get("ipo_id") or "?")
    trend = score_mod.gmp_trend(ipo.get("history") or [])
    arrow = TREND_ARROW.get(trend, "→")
    gmp = ipo.get("gmp")
    price = ipo.get("price_high")
    gmp_pct = ipo.get("gmp_pct")
    conf = esc(ipo.get("confidence") or "n/a")
    lines = [
        f"👍 <b>{esc(name)}</b>",
        (
            f"GMP  <code>₹{_fmt_num(gmp)}</code> on <code>₹{_fmt_num(price)}</code>  =  "
            f"<b>{_fmt_num(gmp_pct, suffix='%')}</b>  {arrow}"
        ),
        (
            f"Quality  {_fmt_num(ipo.get('n_sources'))} sources · "
            f"{_fmt_num(ipo.get('spread_pct'), suffix='%')} spread · {conf}"
        ),
    ]
    if prev is not None:
        lines.append(
            "Sub (prior)  "
            f"QIB {_fmt_x(prev.get('sub_qib'))} · "
            f"NII {_fmt_x(prev.get('sub_nii'))} · "
            f"Ret {_fmt_x(prev.get('sub_retail'))} · "
            f"<b>{_fmt_x(prev.get('sub_total'))}</b>"
        )
    else:
        lines.append("Sub (prior)  n/a")
    lines.append(f"Live book    {_fmt_x((live or ipo).get('sub_total'))}")
    lot = _lot_line(ipo)
    if lot:
        lines.append(lot)
    close = ipo.get("close_date")
    if close:
        lines.append(f"Closes       {esc(_date_heading(str(close)))}")
    return "\n".join(lines)


def render_thumb_down(ipo: dict[str, Any], reasons: list[str]) -> str:
    name = _short_name(ipo.get("name") or ipo.get("ipo_id") or "?")
    reason = reasons[0] if reasons else "did not pass filters"
    gmp_pct = ipo.get("gmp_pct")
    gmp_bit = f" · {_fmt_num(gmp_pct, suffix='%')}" if gmp_pct is not None else ""
    return f"👎 <b>{esc(name)}</b>{gmp_bit}\n    <i>{esc(reason)}</i>"


def render_dm(
    date_iso: str,
    items: list[
        tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]
    ],
) -> str:
    ups = [x for x in items if x[1]]
    downs = [x for x in items if not x[1]]
    parts = [
        f"<b>Closing today</b>",
        f"<i>{esc(_date_heading(date_iso))}</i>",
        "",
        RULE,
    ]
    if ups:
        parts.extend(["", f"<b>Consider filing · {len(ups)}</b>", ""])
        for ipo, _ok, _reasons, prev, live in ups:
            parts.append(render_thumb_up(ipo, prev=prev, live=live))
            parts.append("")
    if downs:
        parts.extend([f"<b>Skip · {len(downs)}</b>", ""])
        for ipo, _ok, reasons, _prev, _live in downs:
            parts.append(render_thumb_down(ipo, reasons))
        parts.append("")
    if not ups and not downs:
        parts.extend(["", "No issues to show.", ""])
    parts.append(DISCLAIMER)
    return "\n".join(parts).strip()


def render_channel(date_iso: str, ipos: list[dict[str, Any]]) -> str:
    parts = [
        "<b>Closing today</b>",
        f"<i>{esc(_date_heading(date_iso))}</i>",
        "",
        RULE,
        "",
    ]
    for ipo in ipos:
        name = _short_name(ipo.get("name") or "?")
        board = ipo.get("board") or "n/a"
        parts.append(f"<b>{esc(name)}</b>  ·  {esc(board)}")
        parts.append(
            f"GMP  <code>₹{_fmt_num(ipo.get('gmp'))}</code> on "
            f"<code>₹{_fmt_num(ipo.get('price_high'))}</code>  =  "
            f"<b>{_fmt_num(ipo.get('gmp_pct'), suffix='%')}</b>"
        )
        parts.append(
            f"Quality  {esc(ipo.get('confidence') or 'n/a')} · "
            f"{_fmt_num(ipo.get('n_sources'))} sources"
        )
        parts.append(
            f"Sub  QIB {_fmt_x(ipo.get('sub_qib'))} · NII {_fmt_x(ipo.get('sub_nii'))} · "
            f"Ret {_fmt_x(ipo.get('sub_retail'))} · <b>{_fmt_x(ipo.get('sub_total'))}</b>"
        )
        parts.append("")
    parts.append(DISCLAIMER)
    return "\n".join(parts).strip()
