"""IPO Guru normalisation and budget (no network)."""

import json

import pytest

from bot import config
from bot.sources import ipoguru

SAMPLE = {
    "slug": "example-industries-ipo",
    "name": "Example Industries Ltd",
    "display_name": "Example Industries",
    "type": "Mainboard",
    "status": "Open",
    "close_date": "2026-09-30",
    "open_date": "2026-09-28",
    "price_band": "140-148",
    "price_min": 140,
    "price_max": 148,
    "lot_size": 101,
    "subscription_total": "1.25",
    "gmp": {"price": "35", "percentage": "23.65%", "updated_at_label": "28 Sep 2026, 11:00 AM IST"},
    "web_url": "https://www.ipoguru.in/ipo/example-industries-ipo",
}


def test_normalize_mainboard():
    row = ipoguru.normalize_row(SAMPLE)
    assert row["ipo_id"] == "example-industries-ipo"
    assert row["name"] == "Example Industries"
    assert row["board"] == "MAIN"
    assert row["price_high"] == 148.0
    assert (row["gmp"], row["gmp_pct"]) == (35.0, 23.65)
    assert row["sub_total"] == 1.25
    assert row["open_date"] == "2026-09-28"


def test_normalize_sme_and_non_equity():
    assert ipoguru.normalize_row({**SAMPLE, "type": "SME"})["board"] == "SME"
    assert ipoguru.normalize_row({**SAMPLE, "type": "Debt"}) is None


def test_gmp_pct_derived_when_missing():
    row = ipoguru.normalize_row({**SAMPLE, "gmp": {"price": "30", "percentage": None}})
    assert row["gmp_pct"] == round(30 / 148 * 100, 2)


@pytest.fixture
def guru_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(ipoguru, "USAGE_PATH", tmp_path / "usage.json")
    monkeypatch.setattr(ipoguru, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setenv("IPOGURU_API_KEY", "k")
    return tmp_path


def test_budget_exhausted_uses_todays_cache_only(guru_paths):
    today = config.today_ist()
    ipoguru.USAGE_PATH.write_text(json.dumps({"date": today, "requests": 10, "last_ts": 0}))
    with pytest.raises(ipoguru.BudgetExceeded):
        ipoguru.fetch_open_ipos()

    ipoguru.CACHE_PATH.write_text(json.dumps({"date": "2026-10-01", "ipos": [{"ipo_id": "old"}]}))
    with pytest.raises(ipoguru.BudgetExceeded):
        ipoguru.fetch_open_ipos()

    ipoguru.CACHE_PATH.write_text(json.dumps({"date": today, "ipos": [{"ipo_id": "fresh"}]}))
    assert ipoguru.fetch_open_ipos() == [{"ipo_id": "fresh"}]
