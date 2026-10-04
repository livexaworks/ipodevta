"""Daily Brief / quiet / channel HTML renderers (model in, HTML out)."""

from __future__ import annotations

import html
import re
from typing import Any

from bot import brief as brief_mod
from bot import copy, fmt
from bot.brief import Brief, BriefRow, ChannelDigest, ChannelRow

VISIBLE_BUDGET = 3800
SKIP_EXPAND_AFTER = 6
SKIP_HARD_CAP = 8


def visible_len(text: str) -> int:
    plain = re.sub(r"<[^>]+>", "", text)
    return len(html.unescape(plain))


def _arrow(row: BriefRow | ChannelRow) -> str:
    return f" {row.trend}" if row.trend else ""


def _gmp_disp(row: BriefRow | ChannelRow) -> str:
    return row.gmp_pct_s or "n/a"


def _closing_fit_card(row: BriefRow, *, drop_categories: bool = False) -> str:
    name = fmt.esc(row.name)
    board = fmt.esc(row.board)
    line1 = f"👍 <b>{name}</b> · {board}"
    if row.lot_cost:
        line1 += f" · {fmt.esc(row.lot_cost)}/lot"
    gmp = fmt.esc(_gmp_disp(row))
    line2 = f"GMP <b>{gmp}</b>{_arrow(row)}"
    if row.est_gain:
        line2 += f" · est. <b>{fmt.esc(row.est_gain)}</b>/lot"
    line3 = f"Sub <b>{fmt.esc(row.sub_prev)}</b> yday"
    if row.sub_now:
        line3 += f" · {fmt.esc(row.sub_now)} now"
    lines = [line1, line2, line3]
    if not drop_categories:
        cats = []
        if row.sub_qib:
            cats.append(f"QIB {row.sub_qib}")
        if row.sub_nii:
            cats.append(f"NII {row.sub_nii}")
        if row.sub_retail:
            cats.append(f"Retail {row.sub_retail}")
        if cats:
            lines.append(" · ".join(cats))
    return "<blockquote>" + "\n".join(lines) + "</blockquote>"


def _closing_check_card(row: BriefRow) -> str:
    name = fmt.esc(row.name)
    board = fmt.esc(row.board)
    line1 = f"⚠️ <b>{name}</b> · {board}"
    line2 = f"GMP {_gmp_disp(row)}{_arrow(row)} · Sub {fmt.esc(row.sub_prev)}"
    lines = [line1, line2]
    if row.reason:
        lines.append(f"<i>{fmt.esc(row.reason)}</i>")
    return "<blockquote>" + "\n".join(lines) + "</blockquote>"


def _closing_skip_line(row: BriefRow) -> str:
    reason = fmt.esc(row.reason or "")
    return f"👎 {fmt.esc(row.name_short)} · <i>{reason}</i>"


def _fits_row(row: BriefRow, *, drop_est: bool = False) -> str:
    name = fmt.esc(row.name)
    board = fmt.esc(row.board)
    line1 = f"<b>{name}</b> · {board} · closes {fmt.esc(row.close_label)}"
    line2 = f"GMP {_gmp_disp(row)}{_arrow(row)} · Sub {fmt.esc(row.sub_prev)}"
    if not drop_est and row.est_gain:
        line2 += f" · est. {fmt.esc(row.est_gain)}/lot"
    return line1 + "\n" + line2


def _wait_row(row: BriefRow) -> str:
    name = fmt.esc(row.name)
    board = fmt.esc(row.board)
    line1 = f"<b>{name}</b> · {board} · closes {fmt.esc(row.close_label)}"
    reason = fmt.esc(row.reason or "")
    line2 = f"GMP {_gmp_disp(row)}{_arrow(row)} · <i>{reason}</i>"
    return line1 + "\n" + line2


def _skip_row(row: BriefRow) -> str:
    reason = fmt.esc(row.reason or "")
    return f"{fmt.esc(row.name_short)} · <i>{reason}</i>"


def _title(b: Brief) -> str:
    emoji = copy.t("emoji.title")
    if b.as_of:
        return (
            f"<b>{emoji} IPO Brief · {fmt.esc(b.title_date)}"
            f" (as of {fmt.esc(b.collect_hhmm)})</b>"
        )
    return f"<b>{emoji} IPO Brief · {fmt.esc(b.title_date)}</b>"


def _section_header(emoji_key: str, label: str, count: int) -> str:
    emoji = copy.t(f"emoji.{emoji_key}")
    return f"<b>{emoji} {label} ({count})</b>"


def _footer(b: Brief) -> str:
    filters = brief_mod.filters_line(b.prefs, b.hidden_count, b.hidden_board)
    data = copy.t("footer.data", hhmm=b.collect_hhmm)
    return f"<i>{fmt.esc(filters)}</i>\n<i>{fmt.esc(data)}</i>"


def render_quiet(b: Brief) -> str:
    emoji = copy.t("emoji.title")
    lines = [
        f"<b>{emoji} IPO Brief · {fmt.esc(b.title_date)}</b>",
        copy.t("brief.quiet_body"),
    ]
    if b.hidden_count:
        key = (
            "brief.quiet_hidden_closing"
            if b.hidden_closing_today
            else "brief.quiet_hidden_open"
        )
        hint = copy.t(
            key,
            count=b.hidden_count,
            board=b.hidden_board,
        )
        lines.append(f"<i>{fmt.esc(hint)}</i>")
    lines.append(f"<i>{fmt.esc(copy.t('footer.quiet_data', hhmm=b.collect_hhmm))}</i>")
    return "\n".join(lines)


def _assemble_brief(
    b: Brief,
    *,
    skip_rows: list[BriefRow],
    skip_more: int,
    fits_rows: list[BriefRow],
    fits_more: int,
    drop_categories: bool,
    drop_est: bool,
    expand_skip: bool,
) -> str:
    parts: list[str] = [_title(b)]

    # Closing today always present
    closing_emoji = copy.t("emoji.closing")
    if not b.closing:
        parts.append(f"\n{closing_emoji} Nothing closes today")
    else:
        parts.append("\n" + _section_header("closing", "Closing today", len(b.closing)))
        body: list[str] = []
        for row in b.closing:
            if row.state == "FIT":
                body.append(_closing_fit_card(row, drop_categories=drop_categories))
            elif row.state == "CHECK":
                body.append(_closing_check_card(row))
            else:
                body.append(_closing_skip_line(row))
        parts.append("\n".join(body))

    if fits_rows or fits_more:
        count = len(fits_rows) + fits_more
        parts.append("\n" + _section_header("fits", "Fits your filters", count))
        block = [_fits_row(r, drop_est=drop_est) for r in fits_rows]
        if fits_more:
            block.append(copy.t("brief.more_fits", count=fits_more))
        parts.append("\n".join(block))

    if b.waiting:
        parts.append("\n" + _section_header("wait", "Too early", len(b.waiting)))
        parts.append("\n".join(_wait_row(r) for r in b.waiting))

    if skip_rows or skip_more:
        count = len(skip_rows) + skip_more
        parts.append("\n" + _section_header("skip", "Skip", count))
        skip_body = [_skip_row(r) for r in skip_rows]
        if skip_more:
            skip_body.append(copy.t("brief.more_skip", count=skip_more))
        joined = "\n".join(skip_body)
        if expand_skip:
            parts.append(f"<blockquote expandable>{joined}</blockquote>")
        else:
            parts.append(joined)

    parts.append("\n" + _footer(b))
    return "\n".join(parts)


def render_brief(b: Brief) -> str:
    if b.quiet:
        return render_quiet(b)

    skip_all = list(b.skip)
    fits_all = list(b.fits)
    drop_categories = False
    drop_est = False

    def attempt(
        skip_rows: list[BriefRow],
        skip_more: int,
        fits_rows: list[BriefRow],
        fits_more: int,
        *,
        expand: bool,
    ) -> str:
        return _assemble_brief(
            b,
            skip_rows=skip_rows,
            skip_more=skip_more,
            fits_rows=fits_rows,
            fits_more=fits_more,
            drop_categories=drop_categories,
            drop_est=drop_est,
            expand_skip=expand,
        )

    expand = len(skip_all) > SKIP_EXPAND_AFTER
    text = attempt(skip_all, 0, fits_all, 0, expand=expand)
    if visible_len(text) <= VISIBLE_BUDGET:
        return text

    # Cut Skip to top 8 by GMP (+ already sorted)
    if len(skip_all) > SKIP_HARD_CAP:
        kept = skip_all[:SKIP_HARD_CAP]
        more = len(skip_all) - SKIP_HARD_CAP
        text = attempt(kept, more, fits_all, 0, expand=True)
        if visible_len(text) <= VISIBLE_BUDGET:
            return text
        skip_all = kept
        skip_more = more
    else:
        skip_more = 0

    drop_categories = True
    text = attempt(skip_all, skip_more, fits_all, 0, expand=True)
    if visible_len(text) <= VISIBLE_BUDGET:
        return text

    drop_est = True
    text = attempt(skip_all, skip_more, fits_all, 0, expand=True)
    if visible_len(text) <= VISIBLE_BUDGET:
        return text

    # Cut Fits until under budget (keep at least 0)
    for keep in range(len(fits_all), -1, -1):
        more = len(fits_all) - keep
        text = attempt(skip_all, skip_more, fits_all[:keep], more, expand=True)
        if visible_len(text) <= VISIBLE_BUDGET:
            return text
    return text


def _channel_line(row: ChannelRow, *, with_board: bool) -> str:
    name = fmt.esc(row.name)
    gmp = _gmp_disp(row)
    arrow = _arrow(row)
    sub = fmt.esc(row.sub_label)
    if row.closing_today:
        board = fmt.esc(row.board)
        return f"{name} · {board} · {gmp}{arrow} · {sub}"
    if with_board:
        return f"{name} · {gmp}{arrow} · {sub} · {fmt.esc(row.close_weekday)}"
    return f"{name} · {gmp}{arrow} · {sub} · {fmt.esc(row.close_weekday)}"


def render_channel_digest(d: ChannelDigest) -> str:
    emoji = copy.t("emoji.title")
    parts = [
        f"<b>{emoji} IPOs open · {fmt.esc(d.title_date)}</b>",
        f"<i>{fmt.esc(copy.t('brief.channel_subtitle'))}</i>",
    ]
    if d.closing:
        parts.append(
            "\n"
            + f"<b>{copy.t('emoji.closing')} Closing today ({len(d.closing)})</b>"
        )
        parts.append("\n".join(_channel_line(r, with_board=True) for r in d.closing))
    if d.main:
        parts.append(f"\n<b>Mainboard ({len(d.main)})</b>")
        parts.append("\n".join(_channel_line(r, with_board=False) for r in d.main))
    if d.sme:
        parts.append(f"\n<b>SME ({len(d.sme)})</b>")
        parts.append("\n".join(_channel_line(r, with_board=False) for r in d.sme))

    data = copy.t("footer.data", hhmm=d.collect_hhmm)
    cta = copy.t("brief.channel_cta", bot=d.bot_username)
    parts.append(f"\n<i>{fmt.esc(data)}</i>")
    parts.append(f"<i>{fmt.esc(cta)}</i>")
    return "\n".join(parts)
