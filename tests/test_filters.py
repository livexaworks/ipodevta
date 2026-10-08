from bot import filters

MAIN = {"board": "MAIN", "gmp_pct": 36.0, "sub_total": 2.0}
SME = {"board": "SME", "gmp_pct": 55.0, "sub_total": 5.0}


def test_defaults_mainboard_only():
    p = filters.normalize({})
    assert p == {"board": "main", "min_gmp_main": 34.0, "min_gmp_sme": 48.0, "min_total_sub": 1.0}
    assert filters.passes(MAIN, {})
    assert not filters.passes(SME, {})


def test_board_both_uses_separate_bars():
    prefs = {"board": "both", "min_gmp_main": 40, "min_gmp_sme": 50}
    assert not filters.passes(MAIN, prefs)
    assert filters.passes(SME, prefs)


def test_sme_only_hides_mainboard():
    assert not filters.passes(MAIN, {"board": "sme"})


def test_subscription_bar():
    assert not filters.passes(MAIN, {"min_total_sub": 2.5})
    assert filters.passes(MAIN, {"min_total_sub": 2})


def test_missing_data_fails():
    assert not filters.passes({**MAIN, "gmp_pct": None}, {})
    assert not filters.passes({**MAIN, "sub_total": None}, {})
    assert not filters.passes({**MAIN, "board": None}, {})


def test_legacy_prefs_still_read():
    legacy = {"min_gmp_pct": 24, "min_total_sub": 1, "include_sme": True}
    p = filters.normalize(legacy)
    assert p["board"] == "both"
    assert p["min_gmp_main"] == 24
    assert p["min_gmp_sme"] == 24
    assert filters.normalize({"min_gmp_pct": 24, "board": "main"})["min_gmp_sme"] == 48
