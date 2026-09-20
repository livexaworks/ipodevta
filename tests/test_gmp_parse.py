"""GMP HTML fixture parsing."""

from pathlib import Path

from bot.sources import gmp

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_investorgain_fixture():
    html = (FIXTURES / "gmp_investorgain.html").read_text(encoding="utf-8")
    rows = gmp.parse_html_fixture(html, "investorgain")
    assert len(rows) > 0
    assert all(isinstance(r["gmp"], (int, float)) or r["gmp"] is None for r in rows)
    assert any(r["gmp"] is not None and isinstance(r["gmp"], float) for r in rows)


def test_ipowatch_fixture_merges_tables():
    html = (FIXTURES / "gmp_ipowatch.html").read_text(encoding="utf-8")
    rows = gmp.parse_html_fixture(html, "ipowatch")
    assert len(rows) >= 4
    names = {r["raw_name"].lower() for r in rows}
    assert any("sonaselection" in n for n in names)
    assert any("kheria" in n for n in names)
    assert all(isinstance(r["gmp"], float) for r in rows if r["gmp"] is not None)


def test_ipocentral_fixture():
    html = (FIXTURES / "gmp_ipocentral.html").read_text(encoding="utf-8")
    rows = gmp.parse_html_fixture(html, "ipocentral")
    assert len(rows) > 0
    assert any(isinstance(r["gmp"], float) for r in rows)


def test_consolidate_confidence():
    quotes = [
        {"gmp": 80.0},
        {"gmp": 88.0},
        {"gmp": 90.0},
    ]
    cons = gmp.consolidate(quotes, 346.0)
    assert cons is not None
    assert cons["confidence"] == "high"
    assert cons["n_sources"] == 3
