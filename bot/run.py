"""Entrypoint.

    python -m bot.run channel            # 9:30 IST: header + one card per open IPO
    python -m bot.run bot                # 14:30 IST: one card per passing IPO to each user
    python -m bot.run bot --dry-run      # print instead of sending, no state writes
    python -m bot.run channel --dry-run --fixture tests/fixtures/market.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from bot import cards, config, filters, state, telegram, worker_api
from bot.collect import CollectError, Collected, collect, is_open_on, order, snapshot_rows
from bot.sources import ipoguru

log = logging.getLogger(__name__)

MODES = (cards.PHASE_CHANNEL, cards.PHASE_BOT)


class Sender(Protocol):
    def send(
        self,
        chat_id: str | int,
        html: str,
        *,
        reply_markup: dict[str, Any] | None = None,
        silent: bool = False,
    ) -> dict[str, Any]: ...


class LiveSender:
    def send(self, chat_id, html, *, reply_markup=None, silent=False):  # noqa: ANN001
        return telegram.send(chat_id, html, reply_markup=reply_markup, silent=silent)


class DryRunSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, chat_id, html, *, reply_markup=None, silent=False):  # noqa: ANN001
        msg = {"chat_id": chat_id, "text": html, "reply_markup": reply_markup, "silent": silent}
        self.sent.append(msg)
        buttons = " | ".join(
            b["text"] for row in (reply_markup or {}).get("inline_keyboard", []) for b in row
        )
        print(f"--- to {chat_id}{' (silent)' if silent else ''} ---\n{html}")
        if buttons:
            print(f"[{buttons}]")
        print()
        return {"message_id": len(self.sent)}


@dataclass
class Report:
    mode: str
    open_ipos: int = 0
    posted: int = 0
    users: int = 0
    no_match: int = 0
    blocked: int = 0
    failed: int = 0
    notes: list[str] = field(default_factory=list)

    def line(self) -> str:
        if self.mode == cards.PHASE_CHANNEL:
            body = f"{self.open_ipos} open IPOs, {self.posted} channel posts"
        else:
            body = (
                f"{self.open_ipos} open IPOs, {self.users} users, {self.posted} cards, "
                f"{self.no_match} no-match, {self.blocked} blocked"
            )
        return f"IPODevta {self.mode}: {body}, {self.failed} failed"


def run_channel(
    ipos: list[dict[str, Any]],
    *,
    today: str,
    as_of: str,
    sent: state.SentLog,
    sender: Sender,
    channel: str,
) -> Report:
    report = Report(cards.PHASE_CHANNEL, open_ipos=len(ipos))
    try:
        if sent.header_id is None:
            msg = sender.send(channel, cards.render_header(ipos, today=today, as_of=as_of))
            sent.set_header(msg["message_id"])
            report.posted += 1
        for ipo in ipos:
            if sent.channel_sent(ipo["ipo_id"]):
                continue
            html = cards.render_card(ipo, today=today, phase=cards.PHASE_CHANNEL, as_of=as_of)
            msg = sender.send(channel, html)
            sent.mark_channel(ipo["ipo_id"], msg["message_id"])
            report.posted += 1
    except telegram.TelegramError as exc:
        report.failed += 1
        report.notes.append(f"channel post failed: {exc}")
        log.error("Channel post failed: %s", exc)
    return report


def run_bot(
    ipos: list[dict[str, Any]],
    users: dict[str, dict[str, Any]],
    *,
    today: str,
    as_of: str,
    sent: state.SentLog,
    sender: Sender,
) -> Report:
    report = Report(cards.PHASE_BOT, open_ipos=len(ipos), users=len(users))
    keyboard = cards.dm_keyboard(sent.header_id)
    rendered = {
        i["ipo_id"]: cards.render_card(i, today=today, phase=cards.PHASE_BOT, as_of=as_of)
        for i in ipos
    }

    for chat_id, prefs in users.items():
        already = set(sent.dm_sent(chat_id))
        passing = [i for i in ipos if filters.passes(i, prefs)]
        try:
            if not passing:
                if state.NO_MATCH not in already:
                    sender.send(chat_id, cards.render_no_match(), reply_markup=keyboard)
                    sent.mark_dm(chat_id, state.NO_MATCH)
                    report.no_match += 1
                continue
            for n, ipo in enumerate(passing):
                if ipo["ipo_id"] in already:
                    continue
                sender.send(chat_id, rendered[ipo["ipo_id"]], reply_markup=keyboard, silent=n > 0)
                sent.mark_dm(chat_id, ipo["ipo_id"])
                report.posted += 1
        except telegram.ChatUnavailable:
            report.blocked += 1
            log.info("User %s blocked the bot or is gone - skipped", state.chat_hash(chat_id))
        except telegram.TelegramError as exc:
            report.failed += 1
            log.warning("DM to %s failed: %s", state.chat_hash(chat_id), exc)
    return report


def market_payload(
    ipos: list[dict[str, Any]], *, today: str, as_of: str, phase: str, header_id: int | None
) -> dict[str, Any]:
    return {
        "date": today,
        "as_of": as_of,
        "phase": phase,
        "today_url": cards.today_url(header_id),
        "ipos": [
            {
                "ipo_id": i["ipo_id"],
                "board": i.get("board"),
                "gmp_pct": i.get("gmp_pct"),
                "sub_total": i.get("sub_total"),
                "card": cards.render_card(i, today=today, phase=phase, as_of=as_of),
            }
            for i in ipos
        ],
    }


def _write_step_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text.rstrip() + "\n")


def _load_fixture(path: str, today: str) -> Collected:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return Collected(ipos=order([r for r in rows if is_open_on(r, today)]))


def run(
    mode: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    fixture: str | None = None,
    only_chat: str | None = None,
) -> int:
    now = config.now_ist()
    today = now.date().isoformat()
    as_of = now.strftime("%H:%M")
    deadline = config.CHANNEL_DEADLINE if mode == cards.PHASE_CHANNEL else config.BOT_DEADLINE

    if not force and not config.is_market_day(today):
        log.info("%s is not a market day - nothing to send", today)
        return 0
    sent = state.SentLog(today, persist=not dry_run)
    if not force and sent.done(mode):
        log.info("%s run already completed for %s", mode, today)
        return 0
    if not force and as_of > deadline:
        msg = f"IPODevta {mode}: run started at {as_of} IST, after the {deadline} cutoff. Skipped to avoid stale posts."
        log.warning(msg)
        if not dry_run:
            telegram.admin(msg)
        return 0

    try:
        collected = _load_fixture(fixture, today) if fixture else collect(today)
    except CollectError as exc:
        log.error("%s", exc)
        if not dry_run:
            telegram.admin(f"IPODevta {mode} aborted, nothing sent: {exc}")
        return 1
    ipos = collected.ipos
    if not dry_run and not fixture:
        state.append_snapshots(snapshot_rows(ipos, date=today, ts=config.format_ist(), phase=mode))

    sender: Sender = DryRunSender() if dry_run else LiveSender()

    def push(notes: list[str]) -> None:
        if dry_run or not config.worker_base_url():
            return
        try:
            worker_api.push_market(
                market_payload(ipos, today=today, as_of=as_of, phase=mode, header_id=sent.header_id)
            )
        except worker_api.WorkerError as exc:
            notes.append(str(exc))

    if mode == cards.PHASE_CHANNEL:
        report = run_channel(
            ipos, today=today, as_of=as_of, sent=sent, sender=sender, channel=config.channel_id()
        )
        push(report.notes)
    else:
        report = Report(cards.PHASE_BOT, open_ipos=len(ipos))
        push(report.notes)
        try:
            users = (
                {only_chat: {}} if only_chat and dry_run else worker_api.fetch_users()
            )
        except worker_api.WorkerError as exc:
            log.error("%s", exc)
            if not dry_run:
                telegram.admin(f"IPODevta bot aborted, no DMs sent: {exc}")
            return 1
        if only_chat:
            users = {only_chat: users.get(only_chat, {})}
        bot_report = run_bot(ipos, users, today=today, as_of=as_of, sent=sent, sender=sender)
        bot_report.notes = report.notes + bot_report.notes
        report = bot_report

    if report.failed == 0 and not only_chat:
        sent.mark_done(mode)

    lines = [report.line(), *collected.warnings, *report.notes]
    if not fixture:
        lines.append(f"IPO Guru calls left today: {ipoguru.usage_remaining()}")
    summary = "\n".join(lines)
    log.info("%s", summary)
    _write_step_summary(summary)
    if not dry_run:
        telegram.admin(summary)
    return 0 if report.failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IPODevta daily runs")
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--dry-run", action="store_true", help="print messages, send nothing, write no state")
    parser.add_argument("--force", action="store_true", help="ignore market-day, deadline and already-done checks")
    parser.add_argument("--fixture", help="JSON list of IPO rows to use instead of live data")
    parser.add_argument("--only-chat", help="bot mode: send to this one chat id only")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    config.load_dotenv()

    try:
        return run(
            args.mode,
            dry_run=args.dry_run,
            force=args.force,
            fixture=args.fixture,
            only_chat=args.only_chat,
        )
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        log.error("Unhandled: %s\n%s", exc, tb)
        if not args.dry_run:
            telegram.admin(f"IPODevta {args.mode} crashed:\n{exc}\n\n{tb[-3000:]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
