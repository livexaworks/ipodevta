"""Pure Daily Brief model: assign each open IPO to exactly one section."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from bot import copy, fmt, score
from bot.prefs import board_mode, gmp_main, gmp_sme
from bot.score import State, Verdict


@dataclass(frozen=True)
class BriefRow:
    ipo_id: str
    name: str
    name_short: str
    board: str  # Main / SME
    board_raw: str
    state: State
    reason: str | None
    gmp_pct: float | None
    gmp_pct_s: str | None
    trend: str
    sub_prev: str
    sub_now: str | None
    sub_qib: str | None
    sub_nii: str | None
    sub_retail: str | None
    lot_cost: str | None
    est_gain: str | None
    close_date: str
    close_label: str
    close_weekday: str


@dataclass
class Brief:
    today: str
    title_date: str
    collect_hhmm: str
    quiet: bool
    closing: list[BriefRow] = field(default_factory=list)
    fits: list[BriefRow] = field(default_factory=list)
    waiting: list[BriefRow] = field(default_factory=list)
    skip: list[BriefRow] = field(default_factory=list)
    hidden_count: int = 0
    hidden_board: str = "IPO"
    hidden_closing_today: bool = False
    prefs: dict[str, Any] = field(default_factory=dict)
    as_of: bool = False

    @property
    def notify(self) -> bool:
        """Sound when Closing today has FIT or CHECK."""
        if self.quiet:
            return False
        return any(r.state in ("FIT", "CHECK") for r in self.closing)


@dataclass(frozen=True)
class ChannelRow:
    ipo_id: str
    name: str
    board: str
    board_raw: str
    gmp_pct: float | None
    gmp_pct_s: str | None
    trend: str
    sub_label: str  # prior-day sub or "day 1"
    close_weekday: str
    closing_today: bool


@dataclass
class ChannelDigest:
    today: str
    title_date: str
    collect_hhmm: str
    closing: list[ChannelRow] = field(default_factory=list)
    main: list[ChannelRow] = field(default_factory=list)
    sme: list[ChannelRow] = field(default_factory=list)
    bot_username: str = "ipodevta"


def _as_today(now: datetime | date | str) -> str:
    if isinstance(now, str):
        return now[:10]
    if isinstance(now, datetime):
        return now.date().isoformat()
    return now.isoformat()


def _history_for(history: list[dict[str, Any]], ipo_id: str) -> list[dict[str, Any]]:
    rows = [h for h in history if h.get("ipo_id") == ipo_id]
    rows.sort(key=lambda r: (r.get("date") or "", r.get("ts") or ""))
    return rows


def _prev_close(hist: list[dict[str, Any]], today: str) -> dict[str, Any] | None:
    prior = [h for h in hist if h.get("date") and h["date"] < today]
    if not prior:
        return None
    last_date = prior[-1]["date"]
    same_day = [h for h in prior if h["date"] == last_date]
    return same_day[-1]


def _gmp_key(row: BriefRow | ChannelRow) -> tuple[bool, float]:
    if row.gmp_pct is None:
        return (True, 0.0)
    return (False, -float(row.gmp_pct))


def _closing_state_rank(state: State) -> int:
    return {"FIT": 0, "CHECK": 1, "SKIP": 2}.get(state, 9)


def _sub_fragment(val: Any) -> str | None:
    if val is None:
        return None
    return fmt.sub(val)


def _build_row(
    ipo: dict[str, Any],
    verdict: Verdict,
    prev: dict[str, Any] | None,
    hist: list[dict[str, Any]],
) -> BriefRow:
    trend_kind = score.gmp_trend(hist)
    arrow = fmt.trend(trend_kind)
    gmp_raw = ipo.get("gmp_pct")
    try:
        gmp_f = float(gmp_raw) if gmp_raw is not None else None
    except (TypeError, ValueError):
        gmp_f = None

    sub_prev_val = None if prev is None else prev.get("sub_total")
    sub_now_s = _sub_fragment(ipo.get("sub_total"))
    # Drop "now" when missing
    if ipo.get("sub_total") is None:
        sub_now_s = None

    qib = _sub_fragment(None if prev is None else prev.get("sub_qib"))
    nii = _sub_fragment(None if prev is None else prev.get("sub_nii"))
    retail = _sub_fragment(None if prev is None else prev.get("sub_retail"))

    close = str(ipo.get("close_date") or "")
    name = str(ipo.get("name") or ipo.get("ipo_id") or "?")
    return BriefRow(
        ipo_id=str(ipo.get("ipo_id") or ""),
        name=fmt.display_name(name),
        name_short=fmt.name_short(name),
        board=fmt.board_label(ipo.get("board")),
        board_raw=str(ipo.get("board") or ""),
        state=verdict.state,
        reason=verdict.reason_text(),
        gmp_pct=gmp_f,
        gmp_pct_s=fmt.gmp_pct(gmp_raw),
        trend=arrow,
        sub_prev=fmt.sub(sub_prev_val),
        sub_now=sub_now_s,
        sub_qib=qib,
        sub_nii=nii,
        sub_retail=retail,
        lot_cost=fmt.lot_cost(ipo.get("price_high"), ipo.get("lot_size")),
        est_gain=fmt.est_gain(ipo.get("gmp"), ipo.get("lot_size")),
        close_date=close,
        close_label=fmt.date_brief(close) if close else "",
        close_weekday=fmt.date_weekday(close) if close else "",
    )


def build_brief(
    ipos: list[dict[str, Any]],
    prefs: dict[str, Any],
    history: list[dict[str, Any]],
    now: datetime | date | str,
    *,
    collect_hhmm: str = "10:55",
    as_of: bool = False,
) -> Brief | None:
    """
    Assign each open IPO to exactly one section.
    Returns None when nothing is open anywhere.
    Quiet Brief when every open IPO is HIDDEN for this user.
    """
    today = _as_today(now)
    if not ipos:
        return None

    closing: list[BriefRow] = []
    fits: list[BriefRow] = []
    waiting: list[BriefRow] = []
    skip: list[BriefRow] = []
    hidden_count = 0
    hidden_boards: dict[str, int] = {}
    hidden_closing = False

    for ipo in ipos:
        hist = _history_for(history, str(ipo.get("ipo_id") or ""))
        prev = _prev_close(hist, today)
        closes_today = str(ipo.get("close_date") or "") == today
        live = {
            "sub_total": ipo.get("sub_total"),
            "sub_qib": ipo.get("sub_qib"),
            "sub_nii": ipo.get("sub_nii"),
            "sub_retail": ipo.get("sub_retail"),
            "board": ipo.get("board"),
        }
        verdict = score.evaluate(
            ipo, live, prev, hist, prefs=prefs, closing_today=closes_today
        )
        if verdict.state == "HIDDEN":
            hidden_count += 1
            label = fmt.board_label(ipo.get("board"))
            hidden_boards[label] = hidden_boards.get(label, 0) + 1
            if closes_today:
                hidden_closing = True
            continue

        row = _build_row(ipo, verdict, prev, hist)
        if closes_today:
            closing.append(row)
        elif verdict.state == "FIT":
            fits.append(row)
        elif verdict.state == "WAIT":
            waiting.append(row)
        else:
            # SKIP (or CHECK that somehow isn't closing — treat as skip)
            skip.append(row)

    if hidden_count == len(ipos):
        # Quiet variant
        if len(hidden_boards) == 1:
            hb = next(iter(hidden_boards))
        else:
            hb = "IPO"
        return Brief(
            today=today,
            title_date=fmt.date_brief(today),
            collect_hhmm=collect_hhmm,
            quiet=True,
            hidden_count=hidden_count,
            hidden_board=hb,
            hidden_closing_today=hidden_closing,
            prefs=dict(prefs),
            as_of=as_of,
        )

    closing.sort(key=lambda r: (_closing_state_rank(r.state), _gmp_key(r)))
    fits.sort(key=lambda r: (r.close_date or "9999", _gmp_key(r)))
    waiting.sort(key=lambda r: (r.close_date or "9999", r.name))
    skip.sort(key=_gmp_key)

    if len(hidden_boards) == 1:
        hb = next(iter(hidden_boards))
    elif hidden_boards:
        hb = "IPO"
    else:
        hb = "IPO"

    return Brief(
        today=today,
        title_date=fmt.date_brief(today),
        collect_hhmm=collect_hhmm,
        quiet=False,
        closing=closing,
        fits=fits,
        waiting=waiting,
        skip=skip,
        hidden_count=hidden_count,
        hidden_board=hb,
        hidden_closing_today=hidden_closing,
        prefs=dict(prefs),
        as_of=as_of,
    )


def filters_line(prefs: dict[str, Any], hidden_count: int, hidden_board: str) -> str:
    mode = board_mode(prefs)
    sub = prefs.get("min_total_sub", 1)
    try:
        sub_s = f"{float(sub):g}"
    except (TypeError, ValueError):
        sub_s = "1"
    if mode == "both":
        text = copy.t(
            "footer.filters_both",
            main=f"{gmp_main(prefs):g}",
            sme=f"{gmp_sme(prefs):g}",
            sub=sub_s,
        )
    else:
        board = "Main" if mode == "main" else "SME"
        gmp = gmp_main(prefs) if mode == "main" else gmp_sme(prefs)
        text = copy.t(
            "footer.filters_one",
            board=board,
            gmp=f"{gmp:g}",
            sub=sub_s,
        )
    if hidden_count > 0:
        text += copy.t(
            "footer.hidden",
            count=hidden_count,
            board=hidden_board,
        )
    return text


def build_channel(
    ipos: list[dict[str, Any]],
    history: list[dict[str, Any]],
    now: datetime | date | str,
    *,
    collect_hhmm: str = "10:55",
    bot_username: str = "ipodevta",
) -> ChannelDigest | None:
    today = _as_today(now)
    if not ipos:
        return None

    rows: list[ChannelRow] = []
    for ipo in ipos:
        hist = _history_for(history, str(ipo.get("ipo_id") or ""))
        prev = _prev_close(hist, today)
        closes_today = str(ipo.get("close_date") or "") == today
        trend_kind = score.gmp_trend(hist)
        gmp_raw = ipo.get("gmp_pct")
        try:
            gmp_f = float(gmp_raw) if gmp_raw is not None else None
        except (TypeError, ValueError):
            gmp_f = None
        if prev is None:
            sub_label = copy.t("brief.day_1")
        else:
            sub_label = fmt.sub(prev.get("sub_total"))
        close = str(ipo.get("close_date") or "")
        name = str(ipo.get("name") or "?")
        rows.append(
            ChannelRow(
                ipo_id=str(ipo.get("ipo_id") or ""),
                name=fmt.display_name(name),
                board=fmt.board_label(ipo.get("board")),
                board_raw=str(ipo.get("board") or ""),
                gmp_pct=gmp_f,
                gmp_pct_s=fmt.gmp_pct(gmp_raw),
                trend=fmt.trend(trend_kind),
                sub_label=sub_label,
                close_weekday=fmt.date_weekday(close) if close else "",
                closing_today=closes_today,
            )
        )

    closing = sorted([r for r in rows if r.closing_today], key=_gmp_key)
    rest = [r for r in rows if not r.closing_today]
    main = sorted([r for r in rest if r.board_raw != "SME"], key=_gmp_key)
    sme = sorted([r for r in rest if r.board_raw == "SME"], key=_gmp_key)
    return ChannelDigest(
        today=today,
        title_date=fmt.date_brief(today),
        collect_hhmm=collect_hhmm,
        closing=closing,
        main=main,
        sme=sme,
        bot_username=bot_username,
    )
