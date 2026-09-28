"""Settings keyboard follows the selected board."""

from bot.keyboards import settings_inline


def _callbacks(prefs):
    rows = settings_inline(prefs)["inline_keyboard"]
    return [btn["callback_data"] for row in rows for btn in row]


def test_mainboard_hides_sme_percentages():
    data = _callbacks({"board": "main", "min_gmp_main": 34, "min_total_sub": 1})
    assert "gmp:main:34" in data
    assert "gmp:ask:main" in data
    assert "sub:1" in data
    assert not any(item.startswith("gmp:sme") for item in data)


def test_sme_hides_mainboard_percentages():
    data = _callbacks({"board": "sme", "min_gmp_sme": 48, "min_total_sub": 1})
    assert "gmp:sme:48" in data
    assert "gmp:ask:sme" in data
    assert "sub:2" in data
    assert not any(item.startswith("gmp:main") for item in data)


def test_both_shows_each_gmp_and_subscription():
    data = _callbacks(
        {
            "board": "both",
            "min_gmp_main": 34,
            "min_gmp_sme": 48,
            "min_total_sub": 5,
        }
    )
    assert "gmp:main:34" in data
    assert "gmp:ask:main" in data
    assert "gmp:sme:48" in data
    assert "gmp:ask:sme" in data
    assert "sub:5" in data
    assert "board:main" in data and "board:sme" in data and "board:both" in data
