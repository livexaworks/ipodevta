"""IPO Guru normalize + budget helpers (no live network)."""

from bot.sources import gmp, ipoguru


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
    "gmp": {
        "price": "35",
        "percentage": "23.65%",
        "updated_at": "2026-09-28T05:30:00.000000Z",
        "updated_at_label": "28 Sep 2026, 11:00 AM IST",
    },
    "web_url": "https://www.ipoguru.in/ipo/example-industries-ipo",
}


def test_normalize_mainboard():
    row = ipoguru.normalize_row(SAMPLE)
    assert row is not None
    assert row["ipo_id"] == "example-industries-ipo"
    assert row["board"] == "MAIN"
    assert row["price_high"] == 148.0
    assert row["gmp"] == 35.0
    assert row["gmp_pct"] == 23.65
    assert row["sub_total"] == 1.25
    assert row["confidence"] == "high"
    assert row["n_sources"] == 1


def test_normalize_sme():
    row = ipoguru.normalize_row({**SAMPLE, "type": "SME", "slug": "sme-co-ipo"})
    assert row is not None
    assert row["board"] == "SME"


def test_normalize_skips_non_equity():
    assert ipoguru.normalize_row({**SAMPLE, "type": "Debt"}) is None


def test_from_ipoguru_helper():
    row = ipoguru.normalize_row(SAMPLE)
    cons = gmp.from_ipoguru(row)
    assert cons is not None
    assert cons["confidence"] == "high"
    assert cons["gmp"] == 35.0


def test_gmp_pct_derived_when_percentage_missing():
    sample = {
        **SAMPLE,
        "gmp": {"price": "30", "percentage": None},
    }
    row = ipoguru.normalize_row(sample)
    assert row is not None
    assert row["gmp"] == 30.0
    assert row["gmp_pct"] == round(30 / 148 * 100, 2)
