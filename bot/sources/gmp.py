"""GMP helpers for the IPO Guru single-source feed.

HTML scrapers (InvestorGain / IPOWatch / IPOCentral) were removed for compliance
and to stay within the IPO Guru free-plan quota.
"""

from __future__ import annotations

from typing import Any


def from_ipoguru(ipo: dict[str, Any]) -> dict[str, Any] | None:
    """Return consolidated GMP fields already present on an IPO Guru row."""
    if ipo.get("gmp") is None or not ipo.get("price_high"):
        return None
    return {
        "gmp": ipo.get("gmp"),
        "gmp_pct": ipo.get("gmp_pct"),
        "n_sources": ipo.get("n_sources") or 1,
        "spread_pct": ipo.get("spread_pct") if ipo.get("spread_pct") is not None else 0.0,
        "confidence": ipo.get("confidence") or "high",
    }
