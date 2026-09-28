"""Entrypoint: python -m bot.run --mode snapshot|alert|dry-run"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from typing import Any

from bot import config, match, notify, render, score, state, users
from bot.sources import bse, gmp, ipoguru

log = logging.getLogger(__name__)


class AbortBroadcast(Exception):
    """Fatal data problem - alert admin, send nothing to channel/users."""


def _history_for(snapshots: list[dict[str, Any]], ipo_id: str) -> list[dict[str, Any]]:
    rows = [s for s in snapshots if s.get("ipo_id") == ipo_id]
    rows.sort(key=lambda r: (r.get("date") or "", r.get("ts") or ""))
    return rows


def _prev_close(history: list[dict[str, Any]], today: str) -> dict[str, Any] | None:
    prior = [h for h in history if h.get("date") and h["date"] < today]
    if not prior:
        return None
    # last snapshot on the most recent prior date
    last_date = prior[-1]["date"]
    same_day = [h for h in prior if h["date"] == last_date]
    return same_day[-1]


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


def collect(*, require_gmp: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Hybrid collect:
      - IPO Guru (1 call): open calendar + GMP
      - BSE public APIs: QIB / NII / Retail / Total (no Guru quota)
    Guru failure is fatal. BSE failure is a warning (total sub from Guru still usable).
    """
    warnings: list[str] = []
    try:
        enriched = ipoguru.fetch_open_ipos(allow_network=True)
    except ipoguru.IpoGuruError as exc:
        raise AbortBroadcast(f"IPO Guru: {exc}") from exc

    with_gmp = [i for i in enriched if i.get("gmp") is not None]
    if require_gmp and not with_gmp:
        raise AbortBroadcast("IPO Guru returned open IPOs but no GMP readings")
    if len(with_gmp) < len(enriched):
        warnings.append(
            f"GMP missing for {len(enriched) - len(with_gmp)}/{len(enriched)} open IPOs"
        )

    try:
        bse_rows = bse.load_live_ipos()
        enriched, unmatched = match.attach_bse_subscription(enriched, bse_rows)
        with_bse = sum(1 for i in enriched if i.get("sub_source") == "bse")
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
    return enriched, warnings


def run(mode: str, *, preview_chat_id: str | None = None) -> int:
    dry_run = mode == "dry-run"
    # dry-run behaves like alert for building messages, but sends nothing
    # to the channel. Command DMs always send for real so users get feedback.
    # Single licensed source — require at least one GMP reading on alert/dry-run.
    require_gmp = mode in ("alert", "dry-run")

    today = config.today_ist()
    ts = config.format_ist()

    # Always drain user commands first (replies are never dry-run)
    # Skipped automatically when TELEGRAM_WEBHOOK / WEBHOOK_BASE_URL is set.
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
        from bot import keyboards, preview, preview_cache

        source, items = preview.build_preview(prefs, limit=5)
        messages = render.render_preview(prefs, source, items)
        for i, text in enumerate(messages):
            markup = keyboards.home_inline() if i == len(messages) - 1 else None
            notify.send_message(
                chat_id,
                text,
                reply_markup=markup,
                dry_run=False,
            )
        cache_text = "\n\n".join(messages)
        if preview_cache.publish_user_preview(chat_id, cache_text, prefs, source=source):
            log.info("Preview cache published for %s", chat_id)
        log.info("Preview sent to %s (%s, %d items)", chat_id, source, len(items))
        return 0

    try:
        enriched, warnings = collect(require_gmp=require_gmp)
    except AbortBroadcast as exc:
        notify.admin(f"IPO bot abort ({mode}): {exc}", dry_run=dry_run)
        log.error("%s", exc)
        return 1

    snap_rows = build_snapshot_rows(enriched, ts=ts, today=today)
    if not dry_run:
        state.append_snapshots(snap_rows)
    else:
        # still load existing for prev_close logic
        pass

    all_snaps = state.load_snapshots()
    if dry_run:
        # include in-memory rows for history continuity in this process
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

    # alert / dry-run
    # Channel: one unfiltered digest per day, every issue in the market.
    channel_msgs = render.render_channel(today, enriched)
    if dry_run:
        for i, channel_msg in enumerate(channel_msgs, 1):
            print(f"=== CHANNEL ({i}/{len(channel_msgs)}) ===")
            print(channel_msg)
            print()
    elif channel_msgs and not state.channel_already_sent(today):
        for channel_msg in channel_msgs:
            notify.broadcast(channel_msg, dry_run=False)
        state.mark_channel_sent(today, [c["ipo_id"] for c in enriched])
        log.info("Channel post sent (%d IPOs, %d message(s))", len(enriched), len(channel_msgs))
    elif channel_msgs:
        log.info("Channel already sent for %s - skip", today)

    closing = [ipo for ipo in enriched if ipo.get("close_date") == today]
    if not closing:
        log.info("No IPOs close today (%s). Channel handled. No DMs.", today)
        return 0

    # Personalized DMs
    user_map = state.load_users()
    for chat_id, prefs in user_map.items():
        if not dry_run and state.user_already_sent(today, chat_id):
            log.info("User %s already sent for %s - skip", chat_id, today)
            continue

        items = []
        for ipo in closing:
            hist = _history_for(all_snaps, ipo["ipo_id"])
            # attach history for trend display
            ipo_view = {**ipo, "history": hist}
            prev = _prev_close(hist, today)
            live = {
                "sub_total": ipo.get("sub_total"),
                "sub_qib": ipo.get("sub_qib"),
                "sub_nii": ipo.get("sub_nii"),
                "sub_retail": ipo.get("sub_retail"),
                "board": ipo.get("board"),
            }
            ok, reasons = score.evaluate(ipo_view, live, prev, hist, prefs=prefs)
            items.append((ipo_view, ok, reasons, prev, live))

        messages = render.render_dm(today, items)
        if dry_run:
            for i, msg in enumerate(messages, 1):
                print(f"=== DM {chat_id} ({i}/{len(messages)}) ===")
                print(msg)
                print()
        else:
            for msg in messages:
                notify.dm(chat_id, msg, dry_run=False)
            state.mark_user_sent(today, chat_id, [c["ipo_id"] for c in closing])
            log.info("DM sent to %s (%d message(s))", chat_id, len(messages))

    if warnings and not dry_run:
        notify.admin("IPO bot alert warnings:\n" + "\n".join(warnings[:20]), dry_run=False)

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
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Windows consoles (cp1252) choke on 👍/👎 in dry-run dumps; Actions is UTF-8.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="replace")
            except Exception:  # noqa: BLE001
                pass
    config.load_dotenv()

    try:
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
