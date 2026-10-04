"""Message formatting for channel feed and personalized DMs."""

from __future__ import annotations

import html
from collections import OrderedDict
from typing import Any

from bot import copy, fmt, keyboards, score as score_mod
from bot.prefs import board_mode, gmp_main, gmp_sme
from bot.render_brief import (  # noqa: F401 — public API
    render_brief,
    render_channel_digest,
    render_quiet,
    visible_len,
)

TELEGRAM_MAX_LEN = 4096

# Re-exports for existing call sites / tests
esc = fmt.esc
display_name = fmt.display_name
NAME_CASE_EXCEPTIONS = fmt.NAME_CASE_EXCEPTIONS

DISCLAIMER = copy.t("disclaimer.dm")
RULE = copy.t("rule")
TREND_ARROW = {"rising": "↗", "falling": "↘", "flat": "→"}

SHORT_DESCRIPTION = copy.t("bot.short_description")
BOT_DESCRIPTION = copy.t("bot.description")


def _fmt_num(val: Any, *, suffix: str = "", places: int | None = None) -> str:
    return fmt.fmt_num(val, suffix=suffix, places=places)


def _fmt_x(val: Any) -> str:
    return fmt.fmt_x(val)


def _ipo_label(ipo: dict[str, Any]) -> str:
    raw = ipo.get("name") or ipo.get("ipo_id") or "?"
    return esc(display_name(str(raw)))


def _date_heading(date_iso: str) -> str:
    return fmt.date_heading(date_iso)


def _lot_line(ipo: dict[str, Any]) -> str | None:
    lot = ipo.get("lot_size")
    price = ipo.get("price_high")
    if lot is None:
        return None
    label = copy.t("labels.lot")
    if price is not None:
        try:
            amount = int(lot) * float(price)
            return f"{label}          {int(lot)}  ·  ≈ ₹{amount:,.0f}"
        except (TypeError, ValueError):
            pass
    return f"{label}          {lot}"


def prefs_summary(prefs: dict[str, Any]) -> str:
    mode = board_mode(prefs)
    sub = _fmt_num(prefs.get("min_total_sub"), suffix="x")
    if mode == "sme":
        return "\n".join(
            [
                copy.t("labels.board_sme_line"),
                copy.t("labels.gmp_line", value=_fmt_num(gmp_sme(prefs), suffix="%")),
                copy.t("labels.sub_line", value=sub),
            ]
        )
    if mode == "both":
        return "\n".join(
            [
                copy.t("labels.board_both_line"),
                copy.t("labels.main_gmp_line", value=_fmt_num(gmp_main(prefs), suffix="%")),
                copy.t("labels.sme_gmp_line", value=_fmt_num(gmp_sme(prefs), suffix="%")),
                copy.t("labels.sub_line", value=sub),
            ]
        )
    return "\n".join(
        [
            copy.t("labels.board_main_line"),
            copy.t("labels.gmp_line", value=_fmt_num(gmp_main(prefs), suffix="%")),
            copy.t("labels.sub_line", value=sub),
        ]
    )


def prefs_block(prefs: dict[str, Any]) -> str:
    return (
        f"<b>{copy.t('labels.your_filters')}</b>\n"
        f"<code>{html.escape(prefs_summary(prefs), quote=False)}</code>"
    )


def channel_invite_text() -> str:
    channel = keyboards.channel_url()
    handle = channel.replace("https://t.me/", "@")
    c = copy.load()["channel_invite"]
    return "\n".join(
        [
            c["title"],
            "",
            c["no_filters"],
            "",
            c["body"],
            "",
            copy.t("channel_invite.join", channel=channel, handle=handle),
            "",
            c["closing"],
        ]
    )


def welcome_text(prefs: dict[str, Any]) -> str:
    channel = keyboards.channel_url()
    w = copy.load()["welcome"]
    return "\n".join(
        [
            w["title"],
            w["tagline"],
            "",
            w["lead"],
            w["bullet_verdict"],
            w["bullet_numbers"],
            w["bullet_filters"],
            "",
            prefs_block(prefs),
            "",
            w["buttons_hint"],
            "",
            copy.t("welcome.channel_invite", channel=channel),
            "",
            w["feedback_hint"],
            "",
            w["closing"],
        ]
    )


def help_text() -> str:
    """At most 8 lines of explanation; long disclaimer lives here."""
    channel = keyboards.channel_url()
    h = copy.load()["help"]
    long_disc = copy.t("disclaimer.long")
    return "\n".join(
        [
            h["title"],
            h["sections"],
            h["check"],
            h["hidden"],
            h["actions"],
            h["feedback"],
            copy.t("help.open_channel", channel=channel),
            f"<blockquote expandable>{long_disc}</blockquote>",
        ]
    )


def settings_text(prefs: dict[str, Any]) -> str:
    mode = board_mode(prefs)
    s = copy.load()["settings"]
    if mode == "sme":
        hint = s["hint_sme"]
    elif mode == "both":
        hint = s["hint_both"]
    else:
        hint = s["hint_main"]
    return "\n".join(
        [
            s["title"],
            "",
            prefs_block(prefs),
            "",
            hint,
            s["tap_hint"],
            s["filters_use"],
            s["channel_note"],
        ]
    )


def gmp_prompt(which: str) -> str:
    g = copy.load()["gmp_prompt"]
    if which == "sme":
        title = g["title_sme"]
        example = "48"
    else:
        title = g["title_main"]
        example = "34"
    return "\n".join(
        [
            title,
            "",
            copy.t("gmp_prompt.body", example=example),
            g["cancel"],
        ]
    )


def feedback_prompt() -> str:
    f = copy.load()["feedback"]
    return "\n".join(
        [
            f["title"],
            "",
            f["body"],
            f["forward"],
            "",
            f["cancel"],
        ]
    )


def render_preview(
    prefs: dict[str, Any],
    source: str,
    items: list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]],
) -> list[str]:
    p = copy.load()["preview"]
    note = p["note_live"] if source == "live" else p["note_processed"]

    header = "\n".join(
        [
            f"<b>{copy.t('labels.preview')}</b>",
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
                p["empty_1"],
                p["empty_2"],
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
    prior_label = copy.t("labels.subscription_prior")
    if prev is not None:
        lines.extend(
            [
                prior_label,
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
        lines.extend([prior_label, copy.t("na"), ""])

    lines.append(f"{copy.t('labels.live_book')}    {_fmt_x((live or ipo).get('sub_total'))}")
    lot = _lot_line(ipo)
    if lot:
        lines.append(lot)
    close = ipo.get("close_date")
    if close:
        lines.append(f"{copy.t('labels.closes')}       {esc(_date_heading(str(close)))}")
    return "\n".join(lines)


# Back-compat aliases used by older call sites / imports
def render_thumb_up(
    ipo: dict[str, Any], *, prev: dict[str, Any] | None, live: dict[str, Any] | None
) -> str:
    return render_match_card(ipo, prev=prev, live=live)


def render_thumb_down(ipo: dict[str, Any], reasons: list[str]) -> str:
    reason = reasons[0] if reasons else copy.t("labels.did_not_pass")
    return "\n".join([_ipo_label(ipo), esc(reason)])


def _matches_section(
    ups: list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]],
) -> str:
    lines = [f"<b>{copy.t('labels.matches_header')}</b>"]
    if not ups:
        lines.append(copy.t("labels.none_today"))
        return "\n".join(lines)
    cards = [render_match_card(ipo, prev=prev, live=live) for ipo, _ok, _r, prev, live in ups]
    lines.append("")
    lines.append("\n\n".join(cards))
    return "\n".join(lines)


def _skipped_section(
    downs: list[tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]],
) -> str:
    lines = [f"<b>{copy.t('labels.skipped_header')}</b>"]
    if not downs:
        lines.append(copy.t("labels.none_today"))
        return "\n".join(lines)

    groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for ipo, _ok, reasons, _prev, _live in downs:
        reason = reasons[0] if reasons else copy.t("labels.did_not_pass")
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

    trunc = "\n\n" + copy.t("messages.truncated")
    return [first[: TELEGRAM_MAX_LEN - 20] + trunc, second[: TELEGRAM_MAX_LEN - 20] + trunc]


def render_dm(
    date_iso: str,
    items: list[
        tuple[dict[str, Any], bool, list[str], dict[str, Any] | None, dict[str, Any] | None]
    ],
) -> list[str]:
    header = "\n".join(
        [
            f"<b>{copy.t('labels.closing_today')}</b>",
            f"<i>{esc(_date_heading(date_iso))}</i>",
        ]
    )
    return _pack_scored_messages(header, items)


def render_channel(
    date_iso: str,
    ipos: list[dict[str, Any]],
    *,
    history: list[dict[str, Any]] | None = None,
    collect_hhmm: str = "10:55",
) -> list[str]:
    """One unfiltered daily digest. Empty when there is nothing to post."""
    from bot import brief as brief_mod

    digest = brief_mod.build_channel(
        ipos,
        history or [],
        date_iso,
        collect_hhmm=collect_hhmm,
    )
    if digest is None:
        return []
    return [render_channel_digest(digest)]
