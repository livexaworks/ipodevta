"""Daily Brief model + renderers (P3)."""

from __future__ import annotations

from bot import brief as brief_mod
from bot import render
from tests.brief_support import (
    assert_brief_invariants,
    assert_matches_golden,
    build_from_fixture,
    render_channel_fixture,
    render_fixture,
)


def test_busy_day_matches_section5_golden():
    html = render_fixture("busy_day")
    assert html is not None
    assert_matches_golden("busy_day", html)
    b = build_from_fixture("busy_day")
    assert b is not None and not b.quiet
    assert_brief_invariants("busy_day", b, html)
    assert b.notify is True


def test_quiet_all_hidden():
    b = build_from_fixture("quiet_all_hidden")
    assert b is not None and b.quiet
    assert b.hidden_count == 4
    assert b.hidden_closing_today is True
    assert b.notify is False
    html = render.render_brief(b)
    assert_matches_golden("quiet_all_hidden", html)
    assert "Vans Electroengineerings" not in html
    assert "Nothing open on your boards today." in html
    assert "4 SME IPOs close today" in html


def test_no_open_returns_none():
    assert build_from_fixture("no_open") is None
    assert render_fixture("no_open") is None


def test_nothing_closing():
    html = render_fixture("nothing_closing")
    assert html is not None
    assert "Nothing closes today" in html
    assert "Fits your filters" in html
    assert_matches_golden("nothing_closing", html)


def test_data_gaps_wait_and_check():
    b = build_from_fixture("data_gaps")
    assert b is not None
    assert [r.ipo_id for r in b.waiting] == ["day1-wait", "day2-wait"]
    assert b.waiting[0].reason == "verdict tomorrow"
    assert b.waiting[1].reason and "No sub data" in b.waiting[1].reason
    assert len(b.closing) == 1 and b.closing[0].state == "CHECK"
    html = render.render_brief(b)
    assert_matches_golden("data_gaps", html)


def test_html_escape():
    html = render_fixture("html_escape")
    assert html is not None
    assert "S&amp;S Power &lt;Beta&gt;" in html
    assert "<Beta>" not in html
    assert "Ltd" not in html or "Limited" not in html
    assert_matches_golden("html_escape", html)


def test_negative_gmp():
    b = build_from_fixture("negative_gmp")
    assert b is not None
    rows = b.skip or b.closing
    assert rows
    row = rows[0]
    assert row.gmp_pct_s == "-8%"
    assert row.trend == "↓"
    assert row.est_gain == "-₹450"
    assert row.state == "SKIP"
    html = render.render_brief(b)
    assert_matches_golden("negative_gmp", html)


def test_overflow_budget_and_closing_intact():
    ipos = []
    history = []
    # 8 closing + 17 later = 25
    for i in range(8):
        ipos.append(
            {
                "ipo_id": f"close-{i}",
                "name": f"Close Co {i} Limited",
                "board": "MAIN" if i % 2 == 0 else "SME",
                "price_high": 100,
                "lot_size": 100,
                "close_date": "2026-10-05",
                "gmp": 10 + i,
                "gmp_pct": 10 + i * 3,
                "confidence": "high",
                "sub_total": 2.0,
            }
        )
        history.append(
            {
                "ipo_id": f"close-{i}",
                "date": "2026-10-04",
                "gmp_pct": 10 + i * 3,
                "sub_total": 0.5 if i > 5 else 2.0,  # some SKIP on sub
            }
        )
    for i in range(17):
        ipos.append(
            {
                "ipo_id": f"later-{i}",
                "name": f"Later Co {i} Limited",
                "board": "SME" if i % 3 == 0 else "MAIN",
                "price_high": 100,
                "lot_size": 100,
                "close_date": "2026-10-09",
                "gmp": 5 + i,
                "gmp_pct": 5 + i,
                "confidence": "high",
                "sub_total": 0.4,
            }
        )
        history.append(
            {
                "ipo_id": f"later-{i}",
                "date": "2026-10-04",
                "gmp_pct": 5 + i,
                "sub_total": 0.4,
            }
        )
    prefs = {
        "board": "both",
        "min_gmp_main": 34,
        "min_gmp_sme": 48,
        "min_total_sub": 1,
        "min_confidence": "medium",
        "block_falling_gmp": False,
    }
    b = brief_mod.build_brief(ipos, prefs, history, "2026-10-05", collect_hhmm="10:55")
    assert b is not None
    assert len(b.closing) == 8
    html = render.render_brief(b)
    assert render.visible_len(html) <= 3800
    assert "Closing today (8)" in html
    # Closing today rows stay present (names may be shortened on skip lines)
    assert "Close Co" in html
    if len(b.skip) > 6:
        assert "blockquote expandable" in html
    assert_matches_golden("overflow", html)


def test_channel_busy_day_golden():
    html = render_channel_fixture("busy_day")
    assert html is not None
    assert "IPOs open" in html
    assert "Closing today (3)" in html
    assert "Mainboard (3)" in html
    assert "SME (1)" in html
    assert "@ipodevta" in html
    # Each IPO once; closing names not repeated under board sections
    for name in (
        "Orvex Cables",
        "Lumora Agritech",
        "Hiraal Foods",
        "Kestrel Auto",
        "Zenqor Infra",
        "Trivant Pharma",
        "Velmora Textiles",
    ):
        assert html.count(name) == 1
    assert html.index("Lumora Agritech") < html.index("Mainboard")
    assert html.index("Kestrel Auto") < html.index("Zenqor Infra")
    assert "day 1" in html
    assert_matches_golden("channel_busy_day", html)


def test_channel_no_open_sends_nothing():
    assert render_channel_fixture("no_open") is None
    assert render.render_channel("2026-10-05", []) == []


def test_each_ipo_once_in_busy_day():
    b = build_from_fixture("busy_day")
    assert b is not None
    ids = [r.ipo_id for r in (*b.closing, *b.fits, *b.waiting, *b.skip)]
    assert len(ids) == len(set(ids))
    assert set(ids) == {
        "orvex-cables",
        "lumora-agritech",
        "hiraal-foods",
        "trivant-pharma",
        "zenqor-infra",
        "kestrel-auto",
        "velmora-textiles",
    }
