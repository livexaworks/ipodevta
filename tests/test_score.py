"""Gate evaluation - prior-day subscription, not live 11:00 QIB."""

from bot import score


def _ipo(**kwargs):
    base = {
        "board": "MAIN",
        "gmp_pct": 25.4,
        "confidence": "high",
        "gmp": 88.0,
        "name": "Vikram Solar",
    }
    base.update(kwargs)
    return base


def test_live_qib_zero_prior_ok_is_thumbs_up():
    """The whole point: live QIB 0.0 must not gate; prior-day QIB 2.1 still 👍."""
    ipo = _ipo()
    live = {"sub_qib": 0.0, "sub_total": 1.8, "board": "MAIN"}
    prev = {"sub_qib": 2.1, "sub_nii": 8.4, "sub_retail": 6.2, "sub_total": 5.9}
    history = [
        {"gmp_pct": 20.0},
        {"gmp_pct": 22.0},
        {"gmp_pct": 24.0},
        {"gmp_pct": 25.0},
    ]
    ok, reasons = score.evaluate(ipo, live, prev, history)
    assert ok is True
    assert reasons == []


def test_insufficient_history():
    ipo = _ipo()
    ok, reasons = score.evaluate(ipo, {"sub_total": 10}, None, [])
    assert ok is False
    assert "insufficient history" in reasons


def test_sme_excluded_by_default():
    ipo = _ipo(board="SME")
    prev = {"sub_total": 5.0}
    ok, reasons = score.evaluate(ipo, None, prev, [])
    assert ok is False
    assert any("SME" in r for r in reasons)


def test_sme_allowed_with_prefs():
    ipo = _ipo(board="SME")
    prev = {"sub_total": 5.0}
    ok, reasons = score.evaluate(
        ipo, None, prev, [], prefs={"include_sme": True, "min_gmp_pct": 24, "min_total_sub": 1}
    )
    assert ok is True


def test_gmp_below_bar():
    ipo = _ipo(gmp_pct=4.2)
    prev = {"sub_total": 5.0}
    ok, reasons = score.evaluate(ipo, None, prev, [])
    assert ok is False
    assert any("below" in r for r in reasons)


def test_user_higher_gmp_bar():
    ipo = _ipo(gmp_pct=25.0)
    prev = {"sub_total": 5.0}
    ok, _ = score.evaluate(ipo, None, prev, [], prefs={"min_gmp_pct": 30.0})
    assert ok is False
