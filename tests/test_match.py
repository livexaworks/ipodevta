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


def test_attach_bse_subscription_copies_categories():
    guru = [
        {
            "ipo_id": "srit-india-ipo",
            "name": "SRIT India",
            "board": "MAIN",
            "gmp": 34.0,
            "sub_total": 1.0,
            "sub_qib": None,
            "sub_nii": None,
            "sub_retail": None,
        }
    ]
    bse_rows = [
        {
            "name": "SRIT INDIA LIMITED",
            "board": "MAIN",
            "ipo_no": "8001",
            "sub_qib": 0.5,
            "sub_nii": 2.1,
            "sub_retail": 3.4,
            "sub_total": 2.0,
        }
    ]
    out, unmatched = match.attach_bse_subscription(guru, bse_rows)
    assert unmatched == []
    assert out[0]["sub_qib"] == 0.5
    assert out[0]["sub_nii"] == 2.1
    assert out[0]["sub_retail"] == 3.4
    assert out[0]["sub_total"] == 2.0  # BSE total wins
    assert out[0]["ipo_no"] == "8001"
    assert out[0]["sub_source"] == "bse"


def test_attach_bse_rejects_board_mismatch():
    guru = [{"ipo_id": "x-ipo", "name": "Example Co", "board": "MAIN", "sub_total": 1.0}]
    bse_rows = [
        {
            "name": "Example Co Limited",
            "board": "SME",
            "ipo_no": "9",
            "sub_total": 5.0,
            "sub_qib": 1.0,
            "sub_nii": 1.0,
            "sub_retail": 1.0,
        }
    ]
    out, unmatched = match.attach_bse_subscription(guru, bse_rows)
    assert len(unmatched) == 1
    assert unmatched[0].get("reject") == "board_mismatch"
    assert out[0].get("sub_source") is None
    assert out[0]["sub_total"] == 1.0
