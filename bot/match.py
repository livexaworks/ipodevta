"""Fuzzy-match BSE subscription rows onto IPO Guru rows by company name."""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz, process

STOP = {
    "ipo",
    "limited",
    "ltd",
    "india",
    "indian",
    "pvt",
    "private",
    "the",
    "sme",
    "nse",
    "bse",
    "mainboard",
    "company",
    "industries",
    "enterprises",
    "of",
}

THRESHOLD = 86

# Short labels that sources use instead of the legal name
ALIASES = {
    "nse": "national stock exchange",
    "nse ipo": "national stock exchange",
    "national stock exchange": "national stock exchange",
}


def canon(name: Any) -> str:
    t = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    words = t.split()
    filtered = [w for w in words if w not in STOP]
    if filtered:
        out = " ".join(filtered)
    else:
        # e.g. "NSE IPO" - do not collapse to empty
        out = " ".join(words)
    return ALIASES.get(out, out)


def match_one(
    query_name: str,
    candidates: dict[str, str],
    *,
    threshold: int = THRESHOLD,
) -> tuple[str | None, float]:
    """
    candidates: ipo_id -> display name (or any label).
    Returns (ipo_id, score) or (None, score) if below threshold.
    """
    if not candidates:
        return None, 0.0
    q = canon(query_name)
    # Score against canonical ids (dict keys), not display labels.
    keys = list(candidates.keys())
    result = process.extractOne(
        q,
        keys,
        scorer=fuzz.token_set_ratio,
    )
    if result is None:
        return None, 0.0
    match_key, score, _ = result
    if score < threshold:
        return None, float(score)
    return str(match_key), float(score)


def attach_bse_subscription(
    guru_ipos: list[dict[str, Any]],
    bse_ipos: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Fuzzy-match BSE live rows onto IPO Guru rows and copy category subscription.

    Guru remains the identity (slug / ipo_id) and GMP source. BSE supplies
    sub_qib / sub_nii / sub_retail / sub_total (and ipo_no) when matched.
    Returns (enriched_guru_ipos, unmatched_bse_rows).
    """
    by_canon: dict[str, dict[str, Any]] = {}
    for ipo in guru_ipos:
        by_canon[canon(ipo["name"])] = ipo

    candidates = {cid: ipo["name"] for cid, ipo in by_canon.items()}
    claimed: set[str] = set()
    unmatched: list[dict[str, Any]] = []

    for bse in bse_ipos:
        cid, score = match_one(bse["name"], candidates)
        if cid is None or cid in claimed:
            unmatched.append({**bse, "match_score": score})
            continue
        # Soft board check — reject obvious cross-board false positives.
        g = by_canon[cid]
        if g.get("board") and bse.get("board") and g["board"] != bse["board"]:
            unmatched.append({**bse, "match_score": score, "reject": "board_mismatch"})
            continue
        claimed.add(cid)
        g["ipo_no"] = bse.get("ipo_no")
        # Exchange book wins for category totals when present.
        for key in ("sub_qib", "sub_nii", "sub_retail", "sub_total"):
            val = bse.get(key)
            if val is not None:
                g[key] = val
        g["sub_source"] = "bse"

    return list(guru_ipos), unmatched
