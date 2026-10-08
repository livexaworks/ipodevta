"""One IPO card used by both the channel and the bot, plus the channel header,
the no-match message and the DM keyboard."""

from __future__ import annotations

from typing import Any

from bot import config, copy, fmt

PHASE_CHANNEL = "channel"
PHASE_BOT = "bot"


def _subscription_line(ipo: dict[str, Any], *, today: str, phase: str, as_of: str) -> str:
    opens_today = str(ipo.get("open_date") or "") == today
    sub = fmt.sub(ipo.get("sub_total"))
    if phase == PHASE_CHANNEL and opens_today:
        return copy.t("card.sub_not_started")
    if sub is None:
        return copy.t("card.sub_na")
    when = (
        copy.t("card.when_morning")
        if phase == PHASE_CHANNEL
        else copy.t("card.when_live", time=fmt.time_12h(as_of))
    )
    return copy.t("card.sub", sub=sub, when=when)


def render_card(ipo: dict[str, Any], *, today: str, phase: str, as_of: str) -> str:
    """HTML card. Identical text for channel and DM given the same data and phase."""
    board = fmt.board_label(ipo.get("board"))
    tag = ""
    if str(ipo.get("close_date") or "") == today:
        tag = copy.t("card.closes_today")
    elif str(ipo.get("open_date") or "") == today:
        tag = copy.t("card.opens_today")

    price = fmt.rupees(ipo.get("price_high"))
    gmp = fmt.rupees(ipo.get("gmp"))
    gmp_pct = fmt.pct(ipo.get("gmp_pct"))

    lines = [
        f"<b>{fmt.esc(fmt.display_name(str(ipo.get('name') or ipo.get('ipo_id') or '?')))}</b>",
        f"{board} · {tag}" if tag else board,
        copy.t(
            "card.dates",
            open=fmt.date_short(ipo.get("open_date")) or "?",
            close=fmt.date_short(ipo.get("close_date")) or "?",
        ),
        copy.t("card.price", price=price) if price else copy.t("card.price_na"),
        copy.t("card.gmp", gmp=gmp, pct=gmp_pct) if gmp and gmp_pct else copy.t("card.gmp_na"),
        _subscription_line(ipo, today=today, phase=phase, as_of=as_of),
    ]
    return "\n".join(lines)


def render_header(ipos: list[dict[str, Any]], *, today: str, as_of: str) -> str:
    closing = sum(1 for i in ipos if str(i.get("close_date") or "") == today)
    return "\n".join([
        copy.t("header.title", date=fmt.date_long(today)),
        copy.t("header.counts", open=len(ipos), closing=closing),
        copy.t("header.footer", time=fmt.time_12h(as_of)),
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
