"""Entrypoint: python -m bot.run --mode snapshot|alert|dry-run"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from typing import Any

from bot import config, match, notify, render, score, state, users
from bot.sources import bse, gmp
from bot.sources import nse as nse_src

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
        cons = gmp.consolidate(ipo.get("gmp_quotes") or [], ipo.get("price_high"))
        row = {
            "ipo_id": ipo["ipo_id"],
            "ts": ts,
            "date": today,
            "name": ipo["name"],
            "board": ipo["board"],
            "price_high": ipo.get("price_high"),
            "lot_size": ipo.get("lot_size"),
            "close_date": ipo.get("close_date"),
            "ipo_no": ipo.get("ipo_no"),
            "gmp": cons["gmp"] if cons else None,
            "gmp_pct": cons["gmp_pct"] if cons else None,
            "n_sources": cons["n_sources"] if cons else None,
            "spread_pct": cons["spread_pct"] if cons else None,
            "confidence": cons["confidence"] if cons else None,
            "sub_total": ipo.get("sub_total"),
            "sub_qib": ipo.get("sub_qib"),
            "sub_nii": ipo.get("sub_nii"),
            "sub_retail": ipo.get("sub_retail"),
        }
        rows.append(row)
        # mirror consolidated fields onto ipo for scoring/render
        if cons:
            ipo.update(cons)
        else:
            ipo.setdefault("gmp", None)
            ipo.setdefault("gmp_pct", None)
            ipo.setdefault("n_sources", None)
            ipo.setdefault("spread_pct", None)
            ipo.setdefault("confidence", None)
    return rows


def collect(*, require_gmp_sources: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch BSE + GMP (+ optional NSE). Raises AbortBroadcast on fatal issues."""
    warnings: list[str] = []

    try:
        live_ipos = bse.load_live_ipos()
    except (bse.BseError, bse.SourceBroken) as exc:
        raise AbortBroadcast(f"BSE: {exc}") from exc

    # NSE is optional enrichment only (names); v1 does not merge hard
    nse_rows = nse_src.fetch_upcoming()
    if nse_rows:
        log.info("NSE upcoming rows (informational): %d", len(nse_rows))

    quotes, errors = gmp.fetch_all_gmp()
    for err in errors:
        warnings.append(str(err))

    ok_sources = {q["source"] for q in quotes}
    if len(ok_sources) < require_gmp_sources:
        detail = "; ".join(warnings) or "too few GMP sources"
        raise AbortBroadcast(
            f"Fewer than {require_gmp_sources} GMP sources succeeded "
            f"({len(ok_sources)} ok). {detail}"
        )
    if errors:
        # partial success still OK if enough sources - admin note
        log.warning("Some GMP sources failed: %s", errors)

    enriched, unmatched = match.join_gmp_to_ipos(live_ipos, quotes)
    if unmatched:
        sample = ", ".join(u["raw_name"] for u in unmatched[:12])
        warnings.append(f"Unmatched GMP names ({len(unmatched)}): {sample}")
    return enriched, warnings


def run(mode: str, *, preview_chat_id: str | None = None) -> int:
    dry_run = mode == "dry-run"
    alert = mode in ("alert", "dry-run")
    # dry-run behaves like alert for building messages, but sends nothing
    # to the channel. Command DMs always send for real so users get feedback.
    require_gmp = 2 if alert else 1

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
        text = render.render_preview(prefs, source, items)
        if len(text) > 4000:
            text = text[:3900] + "\n\n…truncated."
        notify.send_message(
            chat_id,
            text,
            reply_markup=keyboards.home_inline(),
            dry_run=False,
        )
        if preview_cache.publish_user_preview(chat_id, text, prefs, source=source):
            log.info("Preview cache published for %s", chat_id)
        log.info("Preview sent to %s (%s, %d items)", chat_id, source, len(items))
        return 0

    try:
        enriched, warnings = collect(require_gmp_sources=require_gmp)
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
    closing = [ipo for ipo in enriched if ipo.get("close_date") == today]
    if not closing:
        log.info("No IPOs close today (%s). Silence is correct.", today)
        return 0

    # Channel: one unfiltered feed
    channel_msg = render.render_channel(today, closing)
    if dry_run:
        print("=== CHANNEL ===")
        print(channel_msg)
        print()
    elif not state.channel_already_sent(today):
        notify.broadcast(channel_msg, dry_run=False)
        state.mark_channel_sent(today, [c["ipo_id"] for c in closing])
        log.info("Channel post sent (%d IPOs)", len(closing))
    else:
        log.info("Channel already sent for %s - skip", today)

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

        msg = render.render_dm(today, items)
        if dry_run:
            print(f"=== DM {chat_id} ===")
            print(msg)
            print()
        else:
            notify.dm(chat_id, msg, dry_run=False)
            state.mark_user_sent(today, chat_id, [c["ipo_id"] for c in closing])
            log.info("DM sent to %s", chat_id)

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
