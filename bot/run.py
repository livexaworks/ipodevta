"""Entrypoint: python -m bot.run --mode snapshot|alert|dry-run"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import traceback
from typing import Any

from bot import brief as brief_mod
from bot import config, keyboards, match, notify, render, state, users
from bot.sources import bse, gmp, ipoguru

log = logging.getLogger(__name__)


class AbortBroadcast(Exception):
    """Fatal data problem - alert admin, send nothing to channel/users."""


def _hhmm_from_ts(ts: str) -> str:
    m = re.search(r"T(\d{2}):(\d{2})", ts)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    return "10:55"


def build_snapshot_rows(
    enriched: list[dict[str, Any]],
    *,
    ts: str,
    today: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ipo in enriched:
        cons = gmp.from_ipoguru(ipo)
        row = {
            "ipo_id": ipo["ipo_id"],
            "slug": ipo.get("slug"),
            "ts": ts,
            "date": today,
            "name": ipo["name"],
            "board": ipo["board"],
            "price_high": ipo.get("price_high"),
            "lot_size": ipo.get("lot_size"),
            "close_date": ipo.get("close_date"),
            "ipo_no": ipo.get("ipo_no"),
            "web_url": ipo.get("web_url"),
            "gmp": cons["gmp"] if cons else None,
            "gmp_pct": cons["gmp_pct"] if cons else None,
            "n_sources": cons["n_sources"] if cons else None,
            "spread_pct": cons["spread_pct"] if cons else None,
            "confidence": cons["confidence"] if cons else None,
            "sub_total": ipo.get("sub_total"),
            "sub_qib": ipo.get("sub_qib"),
            "sub_nii": ipo.get("sub_nii"),
            "sub_retail": ipo.get("sub_retail"),
            "sub_source": ipo.get("sub_source"),
            "source": "hybrid",
        }
        rows.append(row)
        if cons:
            ipo.update(cons)
        else:
            ipo.setdefault("gmp", None)
            ipo.setdefault("gmp_pct", None)
            ipo.setdefault("n_sources", None)
            ipo.setdefault("spread_pct", None)
            ipo.setdefault("confidence", None)
    return rows


def collect(
    *, require_gmp: bool = True
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """
    Hybrid collect. Returns (ipos, warnings, stats).
    stats: guru_calls, bse_matched, bse_total, unmatched_names
    """
    warnings: list[str] = []
    stats: dict[str, Any] = {
        "guru_calls": 0,
        "bse_matched": 0,
        "bse_total": 0,
        "unmatched_names": [],
    }
    before = int(ipoguru._usage_today().get("requests") or 0)  # noqa: SLF001
    try:
        enriched = ipoguru.fetch_open_ipos(allow_network=True)
    except ipoguru.IpoGuruError as exc:
        raise AbortBroadcast(f"IPO Guru: {exc}") from exc
    after = int(ipoguru._usage_today().get("requests") or 0)  # noqa: SLF001
    stats["guru_calls"] = max(0, after - before)

    with_gmp = [i for i in enriched if i.get("gmp") is not None]
    if require_gmp and not with_gmp:
        raise AbortBroadcast("IPO Guru returned open IPOs but no GMP readings")
    if len(with_gmp) < len(enriched):
        warnings.append(
            f"GMP missing for {len(enriched) - len(with_gmp)}/{len(enriched)} open IPOs"
        )

    try:
        bse_rows = bse.load_live_ipos()
        stats["bse_total"] = len(bse_rows)
        enriched, unmatched = match.attach_bse_subscription(enriched, bse_rows)
        with_bse = sum(1 for i in enriched if i.get("sub_source") == "bse")
        stats["bse_matched"] = with_bse
        stats["unmatched_names"] = [
            str(u.get("name") or "?") for u in unmatched[:12]
        ]
        log.info("BSE subscription attached to %d/%d Guru IPOs", with_bse, len(enriched))
        if unmatched:
            sample = ", ".join(
                f"{u.get('name')}({u.get('match_score', 0):.0f})" for u in unmatched[:8]
            )
            warnings.append(f"Unmatched BSE rows ({len(unmatched)}): {sample}")
    except (bse.BseError, bse.SourceBroken) as exc:
        warnings.append(f"BSE subscription unavailable: {exc}")
        log.warning("BSE failed (continuing with Guru totals only): %s", exc)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"BSE subscription error: {exc}")
        log.exception("BSE unexpected failure")

    remaining = ipoguru.usage_remaining()
    log.info(
        "Hybrid collect: %d open (%d with GMP); Guru requests left today=%d",
        len(enriched),
        len(with_gmp),
        remaining,
    )
    return enriched, warnings, stats


def _write_step_summary(line: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line.rstrip() + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("GITHUB_STEP_SUMMARY write failed: %s", exc)


def _report_line(
    *,
    guru_calls: int,
    bse_matched: int,
    bse_total: int,
    unmatched: list[str],
    briefs_sent: int,
    briefs_failed: int,
    channel_posted: bool | str,
) -> str:
    unmatched_s = ", ".join(unmatched[:6]) if unmatched else "none"
    return (
        f"Guru calls={guru_calls}; BSE matched {bse_matched}/{bse_total} "
        f"(unmatched: {unmatched_s}); briefs sent={briefs_sent} failed={briefs_failed}; "
        f"channel={channel_posted}"
    )


def run(mode: str, *, preview_chat_id: str | None = None) -> int:
    dry_run = mode == "dry-run"
    require_gmp = mode in ("alert", "dry-run")

    today = config.today_ist()
    ts = config.format_ist()
    collect_hhmm = _hhmm_from_ts(ts)

    try:
        n = users.drain_updates(dry_run=False)
        log.info("Processed %d Telegram updates", n)
    except Exception as exc:  # noqa: BLE001
        log.exception("drain_updates: %s", exc)

    if mode == "commands":
        log.info("Commands-only mode complete.")
        return 0

    if mode == "preview":
        chat_id = preview_chat_id or os.environ.get("PREVIEW_CHAT_ID", "").strip()
        if not chat_id:
            log.error("preview mode requires PREVIEW_CHAT_ID")
            return 1
        prefs = state.get_or_create_user(chat_id)
        from bot import preview, preview_cache

        source, brief = preview.build_brief_preview(prefs)
        if brief is None:
            text = "Nothing to show yet.\nCheck again later."
        else:
            text = render.render_brief(brief)
        notify.send_message(
            chat_id,
            text,
            reply_markup=keyboards.brief_inline(),
            disable_notification=True,
            dry_run=False,
        )
        if preview_cache.publish_user_preview(chat_id, text, prefs, source=source):
            log.info("Preview cache published for %s", chat_id)
        log.info("Preview brief sent to %s (%s)", chat_id, source)
        return 0

    skip_collect = (
        mode == "alert"
        and not dry_run
        and state.alert_already_ran(today)
    )
    warnings: list[str] = []
    stats: dict[str, Any] = {
        "guru_calls": 0,
        "bse_matched": 0,
        "bse_total": 0,
        "unmatched_names": [],
    }
    snap_rows: list[dict[str, Any]] = []

    if skip_collect:
        log.info("Alert already recorded for %s — skip Guru collect", today)
        enriched = state.latest_ipos_for_date(today)
        all_snaps = state.load_snapshots()
        if not enriched:
            report = _report_line(
                guru_calls=0,
                bse_matched=0,
                bse_total=0,
                unmatched=[],
                briefs_sent=0,
                briefs_failed=0,
                channel_posted="already",
            )
            log.info("Alert report: %s", report)
            _write_step_summary(report)
            notify.admin(f"IPO alert report: {report}", dry_run=False)
            return 0
    else:
        try:
            enriched, warnings, stats = collect(require_gmp=require_gmp)
        except AbortBroadcast as exc:
            notify.admin(f"IPO bot abort ({mode}): {exc}", dry_run=dry_run)
            log.error("%s", exc)
            return 1

        snap_rows = build_snapshot_rows(enriched, ts=ts, today=today)
        if not dry_run:
            state.append_snapshots(snap_rows)

        all_snaps = state.load_snapshots()
        if dry_run:
            all_snaps = list(all_snaps) + snap_rows

    for w in warnings:
        log.warning("%s", w)

    if mode == "snapshot":
        if warnings:
            notify.admin(
                "IPO bot snapshot warnings:\n" + "\n".join(warnings[:20]),
                dry_run=dry_run,
            )
        log.info("Snapshot mode complete (%d rows). No broadcast.", len(snap_rows))
        return 0

    # --- alert / dry-run ---
    channel_posted: bool | str = False
    channel_msgs = render.render_channel(
        today, enriched, history=all_snaps, collect_hhmm=collect_hhmm
    )
    if dry_run:
        for i, channel_msg in enumerate(channel_msgs, 1):
            print(f"=== CHANNEL ({i}/{len(channel_msgs)}) ===")
            print(channel_msg)
            print()
        channel_posted = "dry-run" if channel_msgs else False
    elif not channel_msgs:
        log.info("No open IPOs — skip channel")
        channel_posted = False
    elif not state.channel_already_sent(today):
        try:
            # One post per day: a single HTML message.
            notify.broadcast(channel_msgs[0], dry_run=False)
            state.mark_channel_sent(today, [c["ipo_id"] for c in enriched])
            channel_posted = True
            log.info("Channel post sent (%d IPOs)", len(enriched))
        except notify.NotifyError as exc:
            log.error("Channel post failed: %s", exc)
            channel_posted = "failed"
    else:
        log.info("Channel already sent for %s - skip", today)
        channel_posted = "already"

    briefs_sent = 0
    briefs_failed = 0
    user_map = state.load_users()

    for chat_id, prefs in user_map.items():
        if not dry_run and state.brief_already_sent(today, chat_id):
            log.info("User %s already briefed for %s - skip", chat_id, today)
            continue

        brief = brief_mod.build_brief(
            enriched,
            prefs,
            all_snaps,
            today,
            collect_hhmm=collect_hhmm,
        )
        if brief is None:
            log.info("User %s: nothing open - no brief", chat_id)
            continue

        text = render.render_brief(brief)
        silent = not brief.notify

        if dry_run:
            print(f"=== BRIEF {chat_id} quiet={brief.quiet} notify={brief.notify} ===")
            print(text)
            print()
            briefs_sent += 1
            continue

        try:
            notify.dm(
                chat_id,
                text,
                reply_markup=keyboards.brief_inline(),
                disable_notification=silent,
                dry_run=False,
            )
            visible_ids = [
                r.ipo_id
                for r in (*brief.closing, *brief.fits, *brief.waiting, *brief.skip)
            ]
            state.mark_brief_sent(
                today,
                chat_id,
                ipo_ids=visible_ids,
                quiet=brief.quiet,
            )
            briefs_sent += 1
            log.info(
                "Brief sent to %s (quiet=%s notify=%s)",
                chat_id,
                brief.quiet,
                brief.notify,
            )
        except Exception as exc:  # noqa: BLE001
            briefs_failed += 1
            log.warning("Brief failed for %s: %s", chat_id, exc)

    report = _report_line(
        guru_calls=int(stats.get("guru_calls") or 0),
        bse_matched=int(stats.get("bse_matched") or 0),
        bse_total=int(stats.get("bse_total") or 0),
        unmatched=list(stats.get("unmatched_names") or []),
        briefs_sent=briefs_sent,
        briefs_failed=briefs_failed,
        channel_posted=channel_posted,
    )
    log.info("Alert report: %s", report)
    _write_step_summary(report)
    if not dry_run:
        notify.admin(f"IPO alert report: {report}", dry_run=False)
        if warnings:
            notify.admin(
                "IPO bot alert warnings:\n" + "\n".join(warnings[:20]),
                dry_run=False,
            )

    return 0


def run_fixture_dry(
    fixture_name: str,
    *,
    to_admin: bool = False,
) -> int:
    """Render a brief fixture (no Guru calls, no state writes)."""
    from tests.brief_support import build_from_fixture, render_fixture

    text = render_fixture(fixture_name)
    if text is None:
        log.info("Fixture %s → no brief (None)", fixture_name)
        print("(no brief)")
        return 0

    b = build_from_fixture(fixture_name)
    markup = keyboards.brief_inline()
    print(text)
    print("--- keyboard ---")
    print(markup)
    if b is not None:
        print(f"--- notify_sound={b.notify} quiet={b.quiet} ---")

    if to_admin:
        chat = config.admin_chat_id()
        if not chat:
            log.error("ADMIN_CHAT_ID unset")
            return 1
        notify.send_message(
            chat,
            text,
            reply_markup=markup,
            disable_notification=not (b and b.notify),
            dry_run=False,
        )
        log.info("Fixture %s sent to admin %s", fixture_name, chat)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IPO GMP screening bot")
    parser.add_argument(
        "--mode",
        choices=("snapshot", "alert", "dry-run", "commands", "preview"),
        required=True,
    )
    parser.add_argument(
        "--chat-id",
        default=None,
        help="Target chat for --mode preview",
    )
    parser.add_argument(
        "--fixture",
        default=None,
        help="With dry-run: render tests/fixtures/brief/<name>.json (no Guru/state)",
    )
    parser.add_argument(
        "--to-admin",
        action="store_true",
        help="With --fixture: send rendered brief to ADMIN_CHAT_ID",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="replace")
            except Exception:  # noqa: BLE001
                pass
    config.load_dotenv()

    try:
        if args.mode == "dry-run" and args.fixture:
            return run_fixture_dry(args.fixture, to_admin=args.to_admin)
        return run(args.mode, preview_chat_id=args.chat_id)
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        log.error("Unhandled: %s\n%s", exc, tb)
        try:
            notify.admin(f"IPO bot crash ({args.mode}):\n{exc}\n\n{tb[-3000:]}")
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
