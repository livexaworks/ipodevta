"""One IPO card used by both the channel and the bot, plus the channel header,
the no-match message and the DM keyboard."""

from __future__ import annotations

from typing import Any

from bot import config, copy, fmt, hashtags

PHASE_CHANNEL = "channel"
PHASE_BOT = "bot"


def _company(ipo: dict[str, Any]) -> str:
    return fmt.display_name(str(ipo.get("name") or ipo.get("ipo_id") or "?"))


def _line1(ipo: dict[str, Any]) -> str:
    company = fmt.esc(_company(ipo))
    gmp = fmt.rupees(ipo.get("gmp"))
    gmp_pct = fmt.pct(ipo.get("gmp_pct"))
    if gmp and gmp_pct:
        return copy.t("card.line1_gmp", company=company, gmp=gmp, pct=gmp_pct)
    return copy.t("card.line1", company=company)


def _line2(ipo: dict[str, Any], *, today: str) -> str:
    board = fmt.board_label(ipo.get("board"))
    date = fmt.date_full(today) or today
    marker = ""
    if str(ipo.get("close_date") or "") == today:
        marker = copy.t("card.closes_today")
    elif str(ipo.get("open_date") or "") == today:
        marker = copy.t("card.opens_today")
    if marker:
        return copy.t("card.line2_marker", board=board, date=date, marker=marker)
    return copy.t("card.line2", board=board, date=date)


def _price_line(ipo: dict[str, Any]) -> str | None:
    low = fmt.rupees(ipo.get("price_low"))
    high = fmt.rupees(ipo.get("price_high"))
    if low and high and low != high:
        # Spec: ₹210-220 (rupee once).
        high_body = high[1:] if high.startswith("₹") else high
        return copy.t("card.price_band", low=low, high=high_body)
    if high:
        return copy.t("card.price", price=high)
    if low:
        return copy.t("card.price", price=low)
    return None


def _est_listing_line(ipo: dict[str, Any]) -> str | None:
    est = fmt.sum_rupees(ipo.get("price_high"), ipo.get("gmp"))
    return copy.t("card.est_listing", price=est) if est else None


def _subscription_lines(ipo: dict[str, Any], *, today: str, phase: str, as_of: str) -> list[str]:
    opens_today = str(ipo.get("open_date") or "") == today
    if phase == PHASE_CHANNEL and opens_today:
        return [copy.t("card.sub_not_started")]

    out: list[str] = []
    total = fmt.sub(ipo.get("sub_total"))
    if total is not None:
        when = (
            copy.t("card.when_morning")
            if phase == PHASE_CHANNEL
            else copy.t("card.when_live", time=fmt.time_12h(as_of))
        )
        out.append(copy.t("card.sub", sub=total, when=when))

    parts: list[str] = []
    qib = fmt.sub(ipo.get("sub_qib"))
    nii = fmt.sub(ipo.get("sub_nii"))
    retail = fmt.sub(ipo.get("sub_retail"))
    if qib is not None:
        parts.append(copy.t("card.cat_qib", value=qib))
    if nii is not None:
        parts.append(copy.t("card.cat_nii", value=nii))
    if retail is not None:
        parts.append(copy.t("card.cat_retail", value=retail))
    if parts:
        out.append(" | ".join(parts))
    return out


def _dates_line(ipo: dict[str, Any]) -> str | None:
    open_d = fmt.date_short(ipo.get("open_date"))
    close_d = fmt.date_short(ipo.get("close_date"))
    bits: list[str] = []
    if open_d:
        bits.append(copy.t("card.date_open", date=open_d))
    if close_d:
        bits.append(copy.t("card.date_close", date=close_d))
    if not bits:
        return None
    return "📅 " + " | ".join(bits)


def _footer(phase: str) -> list[str]:
    channel = config.channel_mention()
    bot = config.bot_mention()
    if phase == PHASE_BOT:
        return [
            copy.t("card.footer_bot_list", channel=channel),
            copy.t("card.footer_bot_filter"),
        ]
    return [
        copy.t("card.footer_channel_bot", bot=bot),
        copy.t("card.footer_channel_join", channel=channel),
    ]


def _join_sections(sections: list[list[str]]) -> str:
    """Join non-empty sections with a blank line; never emit doubled blanks."""
    blocks = ["\n".join(s) for s in sections if s]
    return "\n\n".join(blocks)


def render_card(ipo: dict[str, Any], *, today: str, phase: str, as_of: str) -> str:
    """HTML card for channel and DM. Omit any line whose data is missing."""
    head = [_line1(ipo), _line2(ipo, today=today)]

    body: list[str] = []
    for line in (
        _price_line(ipo),
        _est_listing_line(ipo),
        *_subscription_lines(ipo, today=today, phase=phase, as_of=as_of),
        _dates_line(ipo),
    ):
        if line:
            body.append(line)

    return _join_sections([
        head,
        body,
        [hashtags.hashtag_line(ipo)],
        _footer(phase),
    ])


def render_header(ipos: list[dict[str, Any]], *, today: str, as_of: str) -> str:
    closing = sum(1 for i in ipos if str(i.get("close_date") or "") == today)
    return _join_sections([
        [
            copy.t("header.title", date=fmt.date_full(today) or today),
            copy.t("header.counts", open=len(ipos), closing=closing),
            copy.t("header.footer", time=fmt.time_12h(as_of)),
        ],
        [config.channel_mention()],
        [copy.t("header.hashtags")],
    ])


def render_no_match() -> str:
    return copy.t("no_match")


def today_url(header_message_id: int | None) -> str:
    base = config.channel_url()
    return f"{base}/{header_message_id}" if header_message_id else base


def dm_keyboard(header_message_id: int | None) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": copy.t("buttons.today_ipos"), "url": today_url(header_message_id)},
                {"text": copy.t("buttons.filters"), "callback_data": "settings"},
            ]
        ]
    }
