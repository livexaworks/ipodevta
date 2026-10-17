"""Hashtag builders for Telegram SEO posts (no I/O)."""

from __future__ import annotations

import re
from typing import Any

from bot import fmt

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def company_hashtag(name: str) -> str:
    """Strip suffixes, drop non-alphanumeric, PascalCase words, append IPO.

    Built from fmt.display_name so casing matches the card's company line and
    acronyms (HD, FX, …) stay intact. Names that already end with IPO are not
    doubled.
    """
    display = fmt.display_name(name)
    words: list[str] = []
    for token in display.split():
        cleaned = _NON_ALNUM.sub("", token)
        if not cleaned:
            continue
        if cleaned.upper() in fmt.NAME_CASE_EXCEPTIONS:
            words.append(cleaned.upper())
        elif cleaned[:1].isdigit():
            # Keep leading digits (e.g. 3B) and capitalise the letter part.
            i = 0
            while i < len(cleaned) and cleaned[i].isdigit():
                i += 1
            words.append(cleaned[:i] + cleaned[i:].capitalize() if i < len(cleaned) else cleaned)
        else:
            words.append(cleaned[:1].upper() + cleaned[1:])
    body = "".join(words) if words else "IPO"
    if body.upper().endswith("IPO"):
        # Preserve existing IPO casing from acronyms; ensure trailing IPO.
        if body.endswith("IPO"):
            return f"#{body}"
        return f"#{body[:-3]}IPO"
    return f"#{body}IPO"


def hashtag_line(ipo: dict[str, Any]) -> str:
    """4–5 tags: company, #IPOGMP, board, #GMPToday, #IPOSubscription."""
    name = str(ipo.get("name") or ipo.get("ipo_id") or "IPO")
    board = "#SMEIPO" if (ipo.get("board") or "").upper() == "SME" else "#MainboardIPO"
    tags = [
        company_hashtag(name),
        "#IPOGMP",
        board,
        "#GMPToday",
        "#IPOSubscription",
    ]
    return " ".join(tags)
