"""Load brief fixtures and render them through build_brief / render_brief."""

from __future__ import annotations

import json
import os
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from bot import brief as brief_mod
from bot import fmt, render, score
from bot.brief import Brief

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "brief"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "brief"

ALLOWED_TAGS = frozenset({"b", "i", "blockquote"})


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES_DIR / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"fixture {name} must be an object")
    return data


def build_from_fixture(name: str) -> Brief | None:
    fixture = load_fixture(name)
    return brief_mod.build_brief(
        fixture.get("ipos") or [],
        fixture["prefs"],
        fixture.get("history") or [],
        fixture["today"],
        collect_hhmm=fixture.get("collect_hhmm") or "10:55",
    )


def render_fixture(name: str) -> str | None:
    b = build_from_fixture(name)
    if b is None:
        return None
    return render.render_brief(b)


def render_channel_fixture(name: str) -> str | None:
    fixture = load_fixture(name)
    digest = brief_mod.build_channel(
        fixture.get("ipos") or [],
        fixture.get("history") or [],
        fixture["today"],
        collect_hhmm=fixture.get("collect_hhmm") or "10:55",
    )
    if digest is None:
        return None
    return render.render_channel_digest(digest)


def golden_path(name: str) -> Path:
    return GOLDEN_DIR / f"{name}.html"


def assert_matches_golden(name: str, actual: str) -> None:
    path = golden_path(name)
    normalized = actual.replace("\r\n", "\n")
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(normalized, encoding="utf-8", newline="\n")
        return
    if not path.is_file():
        raise AssertionError(
            f"missing golden {path}; run with UPDATE_GOLDEN=1 to create it"
        )
    expected = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert normalized == expected, f"golden mismatch for {name}"


class _TagChecker(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.in_blockquote = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"disallowed tag <{tag}>")
        if tag == "blockquote":
            if self.in_blockquote:
                self.errors.append("nested blockquote")
            self.in_blockquote += 1
        elif self.in_blockquote and tag not in ("b", "i"):
            self.errors.append(f"tag <{tag}> inside blockquote")
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unbalanced </{tag}>")
        else:
            self.stack.pop()
        if tag == "blockquote":
            self.in_blockquote = max(0, self.in_blockquote - 1)


def assert_html_safe(text: str) -> None:
    checker = _TagChecker()
    checker.feed(text)
    checker.close()
    assert not checker.errors, checker.errors
    assert not checker.stack, f"unclosed tags: {checker.stack}"


def assert_brief_invariants(name: str, b: Brief, html: str) -> None:
    fixture = load_fixture(name)
    today = fixture["today"]
    prefs = fixture["prefs"]
    history = fixture.get("history") or []

    visible_ids = [r.ipo_id for r in (*b.closing, *b.fits, *b.waiting, *b.skip)]
    assert len(visible_ids) == len(set(visible_ids))

    for ipo in fixture.get("ipos") or []:
        hist = [h for h in history if h.get("ipo_id") == ipo["ipo_id"]]
        prior = [h for h in hist if h.get("date") and h["date"] < today]
        prev = None
        if prior:
            last = prior[-1]["date"]
            prev = [h for h in prior if h["date"] == last][-1]
        closing = ipo.get("close_date") == today
        v = score.evaluate(ipo, ipo, prev, hist, prefs=prefs, closing_today=closing)
        disp = fmt.display_name(ipo["name"])
        if v.state == "HIDDEN":
            assert disp not in html, f"hidden name leaked: {disp}"
        else:
            assert disp in html or fmt.name_short(ipo["name"]) in html

    assert_html_safe(html)
    assert render.visible_len(html) <= 3800
