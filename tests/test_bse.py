"""BSE parsers against saved discover fixtures."""

import json
from pathlib import Path

from bot.sources import bse

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_parse_live_equity_ipos():
    payload = json.loads((FIXTURES / "bse_live.json").read_text(encoding="utf-8"))
    rows = bse.parse_live(payload)
    assert len(rows) > 0
    assert all(r["board"] in ("MAIN", "SME") for r in rows)
    assert all(r["ipo_no"] for r in rows)
    names = " ".join(r["name"].lower() for r in rows)
    assert "sonaselection" in names


def test_parse_subscription_catdem():
    payload = json.loads((FIXTURES / "bse_catdem_7973.json").read_text(encoding="utf-8"))
    sub = bse.parse_subscription(payload)
    assert sub["sub_qib"] == 0.0
    assert sub["sub_nii"] is not None and sub["sub_nii"] > 0
    assert sub["sub_retail"] is not None and sub["sub_retail"] > 0
    assert sub["sub_total"] is not None and sub["sub_total"] > 0


def test_price_band_high():
    assert bse.parse_price_high("94.00 - 99.00") == 99.0
    assert bse.parse_price_high("150.00") == 150.0
    assert bse.parse_price_high(None) is None
