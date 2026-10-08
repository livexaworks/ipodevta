"""Collect today's open IPOs: IPO Guru (calendar + GMP) merged with BSE subscription."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from bot import match
from bot.sources import bse, ipoguru

log = logging.getLogger(__name__)


class CollectError(RuntimeError):
    """Primary feed failed; nothing should be broadcast."""


@dataclass
class Collected:
    ipos: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    bse_matched: int = 0


def is_open_on(ipo: dict[str, Any], today: str) -> bool:
    open_d = str(ipo.get("open_date") or "")
    close_d = str(ipo.get("close_date") or "")
    if not close_d or close_d < today:
        return False
    return not open_d or open_d <= today


def order(ipos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Closing soonest first (closing today leads), then highest GMP%."""
    def key(i: dict[str, Any]) -> tuple[str, float, str]:
        gmp = i.get("gmp_pct")
        return (str(i.get("close_date") or "9999"), -(gmp if gmp is not None else -1e9), str(i.get("name")))

    return sorted(ipos, key=key)


def collect(today: str) -> Collected:
    try:
        guru = ipoguru.fetch_open_ipos()
    except ipoguru.IpoGuruError as exc:
        raise CollectError(f"IPO Guru: {exc}") from exc

    ipos = [i for i in guru if is_open_on(i, today)]
    out = Collected(ipos=ipos)

    missing_gmp = sum(1 for i in ipos if i.get("gmp") is None)
    if missing_gmp:
        out.warnings.append(f"GMP missing for {missing_gmp}/{len(ipos)} open IPOs")

    if ipos:
        try:
            bse_rows = bse.load_live_ipos()
            _, unmatched = match.attach_bse_subscription(ipos, bse_rows)
            out.bse_matched = sum(1 for i in ipos if i.get("sub_source") == "bse")
            if unmatched:
                names = ", ".join(str(u.get("name")) for u in unmatched[:6])
                out.warnings.append(f"BSE rows not matched ({len(unmatched)}): {names}")
        except Exception as exc:  # noqa: BLE001 - BSE is a best-effort enrichment
            out.warnings.append(f"BSE subscription unavailable: {exc}")
            log.warning("BSE failed, continuing with IPO Guru totals: %s", exc)

    out.ipos = order(ipos)
    log.info("Collected %d open IPOs (%d with BSE subscription)", len(ipos), out.bse_matched)
    return out


def snapshot_rows(ipos: list[dict[str, Any]], *, date: str, ts: str, phase: str) -> list[dict[str, Any]]:
    keys = ("ipo_id", "name", "board", "price_high", "open_date", "close_date", "gmp", "gmp_pct",
            "sub_total", "sub_qib", "sub_nii", "sub_retail", "sub_source")
    return [{"date": date, "ts": ts, "phase": phase, **{k: i.get(k) for k in keys}} for i in ipos]
