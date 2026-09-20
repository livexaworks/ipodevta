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

# Bot profile copy (setMyShortDescription / setMyDescription)
SHORT_DESCRIPTION = (
    "IPO fills without the clutter. Clear 👍 / 👎 with GMP and subscription."
)
BOT_DESCRIPTION = (
    "IPODevta removes the clutter from IPO fill decisions.\n\n"
    "You get a simple 👍 or 👎 with GMP and subscription numbers, "
    "using filters you set.\n\n"
    "Tap Feedback anytime to send a note to the team.\n\n"
    "Information only - not investment advice. Read the RHP."
)


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
            return f"Lot          {int(lot)}  ·  ≈ ₹{amount:,.0f}"
        except (TypeError, ValueError):
            pass
    return f"Lot          {lot}"


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
            "<b>IPODevta</b>",
            "<i>IPO fills without the clutter.</i>",
            "",
            "On closing days you get:",
            "• A clear 👍 or 👎 for each issue",
            "• GMP and subscription in one place",
            "• Filters you control",
            "",
            prefs_block(prefs),
            "",
            RULE,
            "",
            "Use the buttons below. No typing needed.",
            "",
            f'Prefer a shared list? <a href="{channel}">Join the channel</a>',
            "",
            "Something off? Tap <b>Feedback</b>.",
            "",
            "<i>No selling. No promotions.</i>",
        ]
    )


def help_text() -> str:
    channel = keyboards.channel_url()
    return "\n".join(
        [
            "<b>What you get</b>",
            "",
            "<b>Preview GMP</b>",
            "Recent issues with your filters applied.",
            "",
            "<b>Settings</b>",
            "Your GMP %, subscription floor, and board.",
            "",
            "<b>Channel</b>",
            "Shared closing-day list without personal filters.",
            "",
            "<b>Feedback</b>",
            "Send a short note to the team.",
            "",
            RULE,
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
            "Tap a value below to change it.",
            "Your next Preview and closing-day notes use the new values.",
        ]
    )


def feedback_prompt() -> str:
    return "\n".join(
        [
            "<b>Feedback</b>",
            "",
            "Send your note in one message.",
            "We will forward it to the team.",
            "",
            "Type <code>cancel</code> to stop.",
        ]
    )


def render_preview(
    prefs: dict[str, Any],
    source: str,
    items: list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]],
) -> str:
    if source == "live":
        heading = "Preview"
        note = "Open issues scored with your filters."
    else:
        heading = "Preview"
        note = "Recent issues scored with your filters."

    if not items:
        return "\n".join(
            [
                f"<b>{esc(heading)}</b>",
                "",
                "Nothing to show yet.",
                "Check again later.",
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
        parts.extend(["", f"<b>Looks good · {len(ups)}</b>", ""])
        for ipo, _ok, _reasons, prev, live in ups:
            parts.append(render_thumb_up(ipo, prev=prev, live=live))
            parts.extend(["", RULE, ""])
    if downs:
        parts.extend([f"<b>Better to skip · {len(downs)}</b>", ""])
        for i, (ipo, _ok, reasons, _prev, _live) in enumerate(downs):
            parts.append(render_thumb_down(ipo, reasons))
            if i < len(downs) - 1:
                parts.append("")
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

    lines = [
        f"👍  <b>{esc(name)}</b>",
        "",
        f"GMP          ₹{_fmt_num(gmp)}  on  ₹{_fmt_num(price)}",
        f"             <b>{_fmt_num(gmp_pct, suffix='%')}</b>  {arrow}",
        "",
    ]
    if prev is not None:
        lines.extend(
            [
                "Subscription (prior close)",
                (
                    f"QIB {_fmt_x(prev.get('sub_qib'))}  ·  "
                    f"NII {_fmt_x(prev.get('sub_nii'))}  ·  "
                    f"Retail {_fmt_x(prev.get('sub_retail'))}"
                ),
                f"Total        <b>{_fmt_x(prev.get('sub_total'))}</b>",
                "",
            ]
        )
    else:
        lines.extend(["Subscription (prior close)", "n/a", ""])

    lines.append(f"Live book    {_fmt_x((live or ipo).get('sub_total'))}")
    lot = _lot_line(ipo)
    if lot:
        lines.append(lot)
    close = ipo.get("close_date")
    if close:
        lines.append(f"Closes       {esc(_date_heading(str(close)))}")
    lines.extend(["", "<b>This looks good · thumbs up</b>"])
    return "\n".join(lines)


def render_thumb_down(ipo: dict[str, Any], reasons: list[str]) -> str:
    name = _short_name(ipo.get("name") or ipo.get("ipo_id") or "?")
    reason = reasons[0] if reasons else "did not pass your filters"
    gmp_pct = ipo.get("gmp_pct")
    lines = [
        f"👎  <b>{esc(name)}</b>",
        "",
        f"GMP          {_fmt_num(gmp_pct, suffix='%')}",
        "",
        "Why skip",
        f"<i>{esc(reason)}</i>",
        "",
        "<b>Better to skip · thumbs down</b>",
    ]
    return "\n".join(lines)


def render_dm(
    date_iso: str,
    items: list[
        tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]
    ],
) -> str:
    ups = [x for x in items if x[1]]
    downs = [x for x in items if not x[1]]
    parts = [
        "<b>Closing today</b>",
        f"<i>{esc(_date_heading(date_iso))}</i>",
        "",
        RULE,
    ]
    if ups:
        parts.extend(["", f"<b>Looks good · {len(ups)}</b>", ""])
        for ipo, _ok, _reasons, prev, live in ups:
            parts.append(render_thumb_up(ipo, prev=prev, live=live))
            parts.extend(["", RULE, ""])
    if downs:
        parts.extend([f"<b>Better to skip · {len(downs)}</b>", ""])
        for i, (ipo, _ok, reasons, _prev, _live) in enumerate(downs):
            parts.append(render_thumb_down(ipo, reasons))
            if i < len(downs) - 1:
                parts.append("")
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
    for i, ipo in enumerate(ipos):
        name = _short_name(ipo.get("name") or "?")
        board = ipo.get("board") or "n/a"
        parts.append(f"<b>{esc(name)}</b>  ·  {esc(board)}")
        parts.append("")
        parts.append(
            f"GMP          ₹{_fmt_num(ipo.get('gmp'))}  on  ₹{_fmt_num(ipo.get('price_high'))}"
        )
        parts.append(f"             <b>{_fmt_num(ipo.get('gmp_pct'), suffix='%')}</b>")
        parts.append("")
        parts.append(
            f"Subscription  QIB {_fmt_x(ipo.get('sub_qib'))}  ·  "
            f"NII {_fmt_x(ipo.get('sub_nii'))}  ·  "
            f"Retail {_fmt_x(ipo.get('sub_retail'))}"
        )
        parts.append(f"Total         <b>{_fmt_x(ipo.get('sub_total'))}</b>")
        if i < len(ipos) - 1:
            parts.extend(["", RULE, ""])
        else:
            parts.append("")
    parts.append(DISCLAIMER)
    return "\n".join(parts).strip()
