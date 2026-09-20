"""Name canonicalisation + fuzzy matching across GMP / exchange sources."""

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


def join_gmp_to_ipos(
    ipos: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Attach matching GMP quotes to each IPO (by canon ipo_id).
    Returns (ipos_with_quotes, unmatched_quotes).
    """
    candidates = {canon(ipo["name"]): ipo["name"] for ipo in ipos}
    buckets: dict[str, list[dict[str, Any]]] = {cid: [] for cid in candidates}
    unmatched: list[dict[str, Any]] = []

    for q in quotes:
        cid, score = match_one(q["raw_name"], candidates)
        if cid is None:
            unmatched.append({**q, "match_score": score})
            continue
        buckets[cid].append(q)

    enriched: list[dict[str, Any]] = []
    for ipo in ipos:
        cid = canon(ipo["name"])
        enriched.append({**ipo, "ipo_id": cid, "gmp_quotes": buckets.get(cid, [])})
    return enriched, unmatched
