"""Delivery message formatting."""

from bot import render


def _ipo(name: str, **extra):
    base = {
        "name": name,
        "ipo_id": name.lower().replace(" ", "-"),
        "gmp": 40,
        "price_high": 100,
        "gmp_pct": 40,
        "board": "MAIN",
        "history": [],
        "lot_size": 10,
        "close_date": "2026-09-28",
    }
    base.update(extra)
    return base


def test_display_name_title_case_and_exceptions():
    assert render.display_name("ACME SOLAR LIMITED") == "Acme Solar"
    assert render.display_name("fx parts ltd") == "FX Parts"
    assert render.display_name("FX INDUSTRIES") == "FX Industries"


def test_escapes_ampersand_in_company_name():
    assert render.esc(render.display_name("A&B Metals Ltd")) == "A&amp;B Metals"


def test_dm_leads_with_matches_shows_none_today():
    msgs = render.render_dm("2026-09-28", [])
    assert len(msgs) == 1
    text = msgs[0]
    assert "👍 Matches your filters" in text
    assert "👎 Skipped" in text
    assert text.index("Matches your filters") < text.index("Skipped")
    assert text.count("None today") == 2
    assert "────" not in text
    assert "<blockquote expandable>" in text
    # bold only on headers (Closing today + two section headers)
    assert text.count("<b>") == 3


def test_dm_groups_skips_by_reason():
    items = [
        (_ipo("Alpha Ltd"), False, ["GMP 10% below 24% bar"], None, None),
        (_ipo("Beta Ltd"), False, ["GMP 10% below 24% bar"], None, None),
        (_ipo("Gamma SME"), False, ["SME issue, excluded"], None, None),
    ]
    text = render.render_dm("2026-09-28", items)[0]
    assert "None today" in text  # matches empty
    # reason once, then both names
    assert text.count("GMP 10% below 24% bar") == 1
    assert "Alpha" in text and "Beta" in text
    assert text.count("SME issue, excluded") == 1
    assert "👎" in text
    # no per-line thumbs-down emoji spam on company lines
    assert text.count("👎") == 1


def test_dm_match_not_bold_company_name():
    prev = {"sub_total": 2.0, "sub_qib": 1.0, "sub_nii": 2.0, "sub_retail": 1.5}
    items = [(_ipo("Delta Power LIMITED"), True, [], prev, {"sub_total": 3.0})]
    text = render.render_dm("2026-09-28", items)[0]
    assert "Delta Power" in text
    assert "<b>Delta Power</b>" not in text
    assert "👎 Skipped" in text
    assert "None today" in text


def test_channel_digest_is_grouped_and_concise():
    msgs = render.render_channel(
        "2026-09-28",
        [
            _ipo("Alpha Ltd", board="MAIN", gmp_pct=20, sub_total=1.2),
            _ipo("Beta Power", board="MAIN", gmp_pct=40, sub_total=2.1),
            _ipo("Gamma SME", board="SME", gmp_pct=55, sub_total=8),
        ],
    )
    assert len(msgs) == 1
    text = msgs[0]
    assert "IPO GMP" in text
    assert "<b>Mainboard</b>" in text
    assert "<b>SME</b>" in text
    assert text.index("Beta Power") < text.index("Alpha")
    assert "Beta Power · 40% · 2.10x" in text
    assert "Gamma SME · 55% · 8.00x" in text
    assert "GMP          " not in text
    assert "<blockquote expandable>" in text


def test_channel_empty_when_nothing_to_post():
    assert render.render_channel("2026-09-28", []) == []


def test_split_when_over_telegram_limit(monkeypatch):
    monkeypatch.setattr(render, "TELEGRAM_MAX_LEN", 400)

    def fat_card(ipo, *, prev, live):
        return "X" * 250 + "\n" + render._ipo_label(ipo)

    monkeypatch.setattr(render, "render_match_card", fat_card)
    ups = [
        (_ipo(f"Co {i}"), True, [], None, None) for i in range(3)
    ]
    downs = [
        (_ipo(f"Skip {i}"), False, ["GMP n/a"], None, None) for i in range(3)
    ]
    msgs = render.render_dm("2026-09-28", ups + downs)
    assert len(msgs) == 2
    assert "Matches your filters" in msgs[0]
    assert "Skipped" in msgs[1]
    assert "<blockquote expandable>" in msgs[1]
    assert all(len(m) <= 400 for m in msgs)
