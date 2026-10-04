"""Gate evaluation - prior-day subscription, not live 11:00 QIB."""

from bot import score
from bot.score import Verdict


def _ipo(**kwargs):
    base = {
        "board": "MAIN",
        "gmp_pct": 36.0,
        "confidence": "high",
        "gmp": 88.0,
        "name": "Vikram Solar",
    }
    base.update(kwargs)
    return base


def test_live_qib_zero_prior_ok_is_fit():
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
    v = score.evaluate(ipo, live, prev, history)
    assert v.state == "FIT"
    assert v.ok is True
    assert v.as_legacy() == (True, [])


def test_day1_missing_prior_is_wait_not_skip():
    ipo = _ipo()
    v = score.evaluate(ipo, {"sub_total": 10}, None, [], closing_today=False)
    assert v.state == "WAIT"
    assert v.reason_code == "NO_PRIOR_SUB"
    assert v.reason_text() == "verdict tomorrow"
    assert v.ok is False


def test_day1_closing_today_is_check():
    ipo = _ipo()
    v = score.evaluate(ipo, {"sub_total": 10}, None, [], closing_today=True)
    assert v.state == "CHECK"
    assert v.reason_code == "NO_PRIOR_SUB"


def test_day2_sub_missing_not_closing_is_wait():
    ipo = _ipo()
    prev = {"sub_total": None, "sub_qib": None}
    v = score.evaluate(ipo, None, prev, [], closing_today=False)
    assert v.state == "WAIT"
    assert v.reason_code == "SUB_MISSING"
    assert "No sub data" in (v.reason_text() or "")


def test_day2_sub_missing_closing_is_check():
    ipo = _ipo()
    prev = {"sub_total": None}
    v = score.evaluate(ipo, None, prev, [], closing_today=True)
    assert v.state == "CHECK"
    assert v.reason_code == "SUB_MISSING"


def test_gmp_missing_closing_is_check():
    ipo = _ipo(gmp_pct=None)
    prev = {"sub_total": 5.0}
    v = score.evaluate(ipo, None, prev, [], closing_today=True)
    assert v.state == "CHECK"
    assert v.reason_code == "GMP_MISSING"


def test_sme_excluded_is_hidden():
    ipo = _ipo(board="SME")
    prev = {"sub_total": 5.0}
    v = score.evaluate(ipo, None, prev, [])
    assert v.state == "HIDDEN"
    assert v.reason_code == "BOARD_SME_EXCLUDED"
    assert "SME" in (v.reason_text() or "")


def test_sme_allowed_with_prefs():
    ipo = _ipo(board="SME")
    prev = {"sub_total": 5.0}
    v = score.evaluate(
        ipo, None, prev, [], prefs={"include_sme": True, "min_gmp_pct": 24, "min_total_sub": 1}
    )
    assert v.state == "FIT"


def test_gmp_below_bar():
    ipo = _ipo(gmp_pct=4.2)
    prev = {"sub_total": 5.0}
    v = score.evaluate(ipo, None, prev, [])
    assert v.state == "SKIP"
    assert v.reason_code == "GMP_BELOW"
    assert v.actual == "4.2"
    assert v.required == "34"
    assert v.reason_text() == "GMP 4.2%, needs 34%"


def test_user_higher_gmp_bar():
    ipo = _ipo(gmp_pct=25.0)
    prev = {"sub_total": 5.0}
    v = score.evaluate(ipo, None, prev, [], prefs={"min_gmp_pct": 30.0})
    assert v.state == "SKIP"
    assert v.reason_code == "GMP_BELOW"
    assert v.required == "30"


def test_main_default_bar_is_34():
    ipo = _ipo(gmp_pct=33)
    prev = {"sub_total": 5.0}
    v = score.evaluate(ipo, None, prev, [])
    assert v.state == "SKIP"
    assert v.reason_code == "GMP_BELOW"
    assert v.required == "34"


def test_sme_default_bar_is_48_when_included():
    ipo = _ipo(board="SME", gmp_pct=47)
    prev = {"sub_total": 5.0}
    v = score.evaluate(ipo, None, prev, [], prefs={"board": "both"})
    assert v.state == "SKIP"
    assert v.reason_code == "GMP_BELOW"
    assert v.required == "48"


def test_sme_only_excludes_mainboard():
    ipo = _ipo(board="MAIN", gmp_pct=80)
    prev = {"sub_total": 5.0}
    v = score.evaluate(ipo, None, prev, [], prefs={"board": "sme"})
    assert v.state == "HIDDEN"
    assert v.reason_code == "BOARD_MAIN_EXCLUDED"


def test_sme_only_uses_sme_bar():
    ipo = _ipo(board="SME", gmp_pct=50)
    prev = {"sub_total": 5.0}
    v = score.evaluate(
        ipo, None, prev, [], prefs={"board": "sme", "min_gmp_sme": 48}
    )
    assert v.state == "FIT"


def test_sub_below_skips():
    ipo = _ipo()
    prev = {"sub_total": 0.7}
    v = score.evaluate(ipo, None, prev, [])
    assert v.state == "SKIP"
    assert v.reason_code == "SUB_BELOW"
    assert v.reason_text() == "Sub 0.7x, needs 1x"


def test_gate_order_gmp_below_beats_sub_below():
    """Primary reason is the first failing evaluable gate in existing order."""
    ipo = _ipo(gmp_pct=10)
    prev = {"sub_total": 0.2}
    v = score.evaluate(ipo, None, prev, [])
    assert v.state == "SKIP"
    assert v.reason_code == "GMP_BELOW"


def test_hard_fail_beats_missing_data():
    """Missing prior sub does not become WAIT/CHECK when GMP also fails."""
    ipo = _ipo(gmp_pct=10)
    v = score.evaluate(ipo, None, None, [], closing_today=True)
    assert v.state == "SKIP"
    assert v.reason_code == "GMP_BELOW"


def test_low_confidence_is_skip():
    ipo = _ipo(confidence="low")
    prev = {"sub_total": 5.0}
    v = score.evaluate(ipo, None, prev, [], prefs={"min_confidence": "medium"})
    assert v.state == "SKIP"
    assert v.reason_code == "LOW_CONFIDENCE"


def test_falling_gmp_is_skip_with_from_to():
    ipo = _ipo(gmp_pct=40)
    prev = {"sub_total": 5.0}
    history = [
        {"gmp_pct": 50.0},
        {"gmp_pct": 48.0},
        {"gmp_pct": 30.0},
        {"gmp_pct": 28.0},
    ]
    v = score.evaluate(ipo, None, prev, history)
    assert v.state == "SKIP"
    assert v.reason_code == "GMP_FALLING"
    text = v.reason_text() or ""
    assert text.startswith("GMP falling,")
    assert "→" in text


def test_as_legacy_hidden_keeps_exclusion_text_for_old_renderer():
    v = Verdict(state="HIDDEN", reason_code="BOARD_SME_EXCLUDED")
    ok, reasons = v.as_legacy()
    assert ok is False
    assert reasons == ["SME issue, excluded"]
