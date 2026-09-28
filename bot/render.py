"""Message formatting for channel feed and personalized DMs."""

from __future__ import annotations

import html
from collections import OrderedDict
from datetime import datetime
from typing import Any

from bot import keyboards, score as score_mod
from bot.prefs import board_mode, gmp_main, gmp_sme

TELEGRAM_MAX_LEN = 4096

DISCLAIMER = (
    "<blockquote expandable>"
    "Grey-market premium is unofficial and can move quickly.\n"
    "Information only - not investment advice. Read the RHP."
    "</blockquote>"
)

# Kept for worker/JS parity and older call sites; delivery messages use blank lines.
RULE = "────────────"
TREND_ARROW = {"rising": "↗", "falling": "↘", "flat": "→"}

# Tokens kept ALL CAPS after .title() normalisation (e.g. "FX Parts").
NAME_CASE_EXCEPTIONS = frozenset({"FX", "NSE", "BSE", "SME", "IPO", "QIB", "NII", "AI", "IT"})

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


def display_name(name: str) -> str:
    """Title-case company names; keep a small ALL-CAPS exception list."""
    short = _short_name(str(name))
    words: list[str] = []
    for word in short.title().split():
        if word.upper() in NAME_CASE_EXCEPTIONS:
            words.append(word.upper())
        else:
            words.append(word)
    return " ".join(words) if words else short


def _ipo_label(ipo: dict[str, Any]) -> str:
    raw = ipo.get("name") or ipo.get("ipo_id") or "?"
    return esc(display_name(str(raw)))


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
    mode = board_mode(prefs)
    sub = _fmt_num(prefs.get("min_total_sub"), suffix="x")
    if mode == "sme":
        return (
            f"Board       SME\n"
            f"GMP         {_fmt_num(gmp_sme(prefs), suffix='%')}\n"
            f"Sub         {sub}"
        )
    if mode == "both":
        return (
            f"Board       Mainboard + SME\n"
            f"Main GMP    {_fmt_num(gmp_main(prefs), suffix='%')}\n"
            f"SME GMP     {_fmt_num(gmp_sme(prefs), suffix='%')}\n"
            f"Sub         {sub}"
        )
    return (
        f"Board       Mainboard\n"
        f"GMP         {_fmt_num(gmp_main(prefs), suffix='%')}\n"
        f"Sub         {sub}"
    )


def prefs_block(prefs: dict[str, Any]) -> str:
    return f"<b>Your filters</b>\n<code>{html.escape(prefs_summary(prefs), quote=False)}</code>"


def channel_invite_text() -> str:
    channel = keyboards.channel_url()
    handle = channel.replace("https://t.me/", "@")
    return "\n".join(
        [
            "<b>Public channel</b>",
            "",
            "No personal filters here.",
            "",
            "Once a day this channel posts a short GMP and subscription list "
            "for the issues in the market. No personal filters. One post, "
            "then it stays quiet until the next day.",
            "",
            f'<a href="{channel}">Join {handle}</a>',
            "",
            "Happy filing. All the best for allotments in the companies you care about.",
        ]
    )


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
            "Use the buttons below. No typing needed.",
            "",
            f'Want closing-day GMP with no filters? <a href="{channel}">Join the public channel</a>',
            "",
            "Something off? Tap <b>Feedback</b>.",
            "",
            "<i>Happy filing. All the best for allotments.</i>",
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
            "Mainboard GMP, SME GMP, subscription floor, and which boards to include.",
            "",
            "<b>Channel</b>",
            "One daily GMP list for every issue in the market. No personal filters.",
            "",
            "<b>Feedback</b>",
            "Send a short note to the team.",
            "",
            f'<a href="{channel}">Open the public channel</a>',
            "",
            DISCLAIMER,
        ]
    )


def settings_text(prefs: dict[str, Any]) -> str:
    mode = board_mode(prefs)
    if mode == "sme":
        hint = "SME percentages are below. Subscription is under that."
    elif mode == "both":
        hint = "Mainboard percentages come first. SME percentages follow. Subscription is under both."
    else:
        hint = "Mainboard percentages are below. Subscription is under that."
    return "\n".join(
        [
            "<b>Settings</b>",
            "",
            prefs_block(prefs),
            "",
            hint,
            "Tap a percentage, or tap <b>Type %</b> and send a number.",
            "Preview and closing-day notes use these filters.",
            "The channel still posts one daily list for everyone.",
        ]
    )


def gmp_prompt(which: str) -> str:
    if which == "sme":
        title = "SME GMP"
        example = "48"
    else:
        title = "Mainboard GMP"
        example = "34"
    return "\n".join(
        [
            f"<b>{title}</b>",
            "",
            f"Send a percentage, for example <code>{example}</code>.",
            "Type <code>cancel</code> to stop.",
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
) -> list[str]:
    if source == "live":
        note = "Open issues scored with your filters."
    else:
        note = "Recent issues scored with your filters."

    header = "\n".join(
        [
            "<b>Preview</b>",
            f"<i>{esc(note)}</i>",
            "",
            prefs_block(prefs),
        ]
    )
    if not items:
        body = "\n".join(
            [
                header,
                "",
                "Nothing to show yet.",
                "Check again later.",
            ]
        )
        return [body]

    return _pack_scored_messages(header, items)


def render_match_card(
    ipo: dict[str, Any], *, prev: dict[str, Any] | None, live: dict[str, Any] | None
) -> str:
    trend = score_mod.gmp_trend(ipo.get("history") or [])
    arrow = TREND_ARROW.get(trend, "→")
    gmp = ipo.get("gmp")
    price = ipo.get("price_high")
    gmp_pct = ipo.get("gmp_pct")

    lines = [
        _ipo_label(ipo),
        "",
        f"GMP          ₹{_fmt_num(gmp)}  on  ₹{_fmt_num(price)}",
        f"             {_fmt_num(gmp_pct, suffix='%')}  {arrow}",
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
                f"Total        {_fmt_x(prev.get('sub_total'))}",
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
    return "\n".join(lines)


# Back-compat aliases used by older call sites / imports
def render_thumb_up(
    ipo: dict[str, Any], *, prev: dict[str, Any] | None, live: dict[str, Any] | None
) -> str:
    return render_match_card(ipo, prev=prev, live=live)


def render_thumb_down(ipo: dict[str, Any], reasons: list[str]) -> str:
    reason = reasons[0] if reasons else "did not pass your filters"
    return "\n".join([_ipo_label(ipo), esc(reason)])


def _matches_section(
    ups: list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]],
) -> str:
    lines = ["<b>👍 Matches your filters</b>"]
    if not ups:
        lines.append("None today")
        return "\n".join(lines)
    cards = [render_match_card(ipo, prev=prev, live=live) for ipo, _ok, _r, prev, live in ups]
    lines.append("")
    lines.append("\n\n".join(cards))
    return "\n".join(lines)


def _skipped_section(
    downs: list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]],
) -> str:
    lines = ["<b>👎 Skipped</b>"]
    if not downs:
        lines.append("None today")
        return "\n".join(lines)

    groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for ipo, _ok, reasons, _prev, _live in downs:
        reason = reasons[0] if reasons else "did not pass your filters"
        groups.setdefault(reason, []).append(ipo)

    blocks: list[str] = []
    for reason, ipos in groups.items():
        block = [esc(reason)]
        block.extend(_ipo_label(ipo) for ipo in ipos)
        blocks.append("\n".join(block))
    lines.append("")
    lines.append("\n\n".join(blocks))
    return "\n".join(lines)


def _pack_scored_messages(
    header: str,
    items: list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]],
) -> list[str]:
    ups = [x for x in items if x[1]]
    downs = [x for x in items if not x[1]]
    matches = _matches_section(ups)
    skipped = _skipped_section(downs)

    single = "\n\n".join([header, matches, skipped, DISCLAIMER])
    if len(single) <= TELEGRAM_MAX_LEN:
        return [single]

    # Busy day: matches first, skipped second (disclaimer on the last message).
    first = "\n\n".join([header, matches])
    second = "\n\n".join([skipped, DISCLAIMER])
    if len(first) <= TELEGRAM_MAX_LEN and len(second) <= TELEGRAM_MAX_LEN:
        return [first, second]

    # Extreme overflow: still return the split; callers may truncate further.
    return [first[: TELEGRAM_MAX_LEN - 20] + "\n\n…truncated.", second[: TELEGRAM_MAX_LEN - 20] + "\n\n…truncated."]


def render_dm(
    date_iso: str,
    items: list[
        tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]
    ],
) -> list[str]:
    header = "\n".join(
        [
            "<b>Closing today</b>",
            f"<i>{esc(_date_heading(date_iso))}</i>",
        ]
    )
    return _pack_scored_messages(header, items)


def _channel_line(ipo: dict[str, Any]) -> str:
    name = esc(display_name(str(ipo.get("name") or "?")))
    gmp = _fmt_num(ipo.get("gmp_pct"), suffix="%")
    sub = _fmt_x(ipo.get("sub_total"))
    return f"{name} · {gmp} · {sub}"


def _gmp_sort_key(ipo: dict[str, Any]) -> tuple[bool, float]:
    raw = ipo.get("gmp_pct")
    if raw is None:
        return (True, 0.0)
    try:
        return (False, -float(raw))
    except (TypeError, ValueError):
        return (True, 0.0)


def render_channel(date_iso: str, ipos: list[dict[str, Any]]) -> list[str]:
    """One concise daily digest. Empty when there is nothing to post."""
    if not ipos:
        return []

    main = [ipo for ipo in ipos if (ipo.get("board") or "MAIN") != "SME"]
    sme = [ipo for ipo in ipos if ipo.get("board") == "SME"]
    main.sort(key=_gmp_sort_key)
    sme.sort(key=_gmp_sort_key)

    sections: list[str] = []
    if main:
        sections.append("<b>Mainboard</b>\n" + "\n".join(_channel_line(ipo) for ipo in main))
    if sme:
        sections.append("<b>SME</b>\n" + "\n".join(_channel_line(ipo) for ipo in sme))
    if not sections:
        return []

    header = "\n".join(
        [
            "<b>IPO GMP</b>",
            f"<i>{esc(_date_heading(date_iso))}</i>",
        ]
    )
    messages: list[str] = []
    buf: list[str] = []
    for section in sections:
        trial_parts = [header, *buf, section, DISCLAIMER]
        if buf and len("\n\n".join(trial_parts)) > TELEGRAM_MAX_LEN:
            messages.append("\n\n".join([header, *buf, DISCLAIMER]))
            buf = [section]
        else:
            buf.append(section)
    if buf:
        head = header if not messages else header + "\n<i>continued</i>"
        messages.append("\n\n".join([head, *buf, DISCLAIMER]))
    return messages
