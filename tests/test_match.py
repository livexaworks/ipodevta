"""Name canonicalisation and fuzzy matching."""

from bot import match


def test_aliases_same_ipo_id():
    a = match.canon("Vikram Solar Limited")
    b = match.canon("Vikram Solar IPO")
    c = match.canon("Vikram Solar")
    assert a == b == c == "vikram solar"


def test_distinct_companies_do_not_match():
    candidates = {
        match.canon("Vikram Solar"): "Vikram Solar",
        match.canon("Sonaselection India"): "Sonaselection India",
    }
    cid, score = match.match_one("Completely Different Corp Ltd", candidates)
    assert cid is None
    assert score < match.THRESHOLD


def test_fuzzy_match_above_threshold():
    candidates = {
        match.canon("Sonaselection India Limited"): "Sonaselection India Limited",
    }
    cid, score = match.match_one("Sonaselection India IPO", candidates)
    assert cid == match.canon("Sonaselection India Limited")
    assert score >= match.THRESHOLD


def test_nse_short_name_does_not_collapse():
    assert match.canon("NSE") == "national stock exchange"
    assert match.canon("NSE IPO") == "national stock exchange"
