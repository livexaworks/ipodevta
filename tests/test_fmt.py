"""Pure formatters for the Daily Brief redesign."""

from bot import fmt


def test_esc_ampersand_and_angles():
    assert fmt.esc("A&B <Beta>") == "A&amp;B &lt;Beta&gt;"
    assert fmt.esc(None) == "n/a"


def test_display_name_strips_suffix_and_title_cases():
    assert fmt.display_name("ACME SOLAR LIMITED") == "Acme Solar"
    assert fmt.display_name("S&S Power <Beta> Ltd") == "S&S Power <Beta>"
    assert fmt.display_name("fx parts ltd.") == "FX Parts"


def test_name_short_ellipsis():
    long = "Really Long Company Name Here Ltd"
    short = fmt.name_short(long, limit=24)
    assert short.endswith("…")
    assert len(short) == 24


def test_gmp_pct_signed_integer():
    assert fmt.gmp_pct(41.2) == "+41%"
    assert fmt.gmp_pct(-8) == "-8%"
    assert fmt.gmp_pct(0) == "0%"
    assert fmt.gmp_pct(None) is None


def test_sub_precision():
    assert fmt.sub(0.6) == "0.6x"
    assert fmt.sub(3.4) == "3.4x"
    assert fmt.sub(142) == "142x"
    assert fmt.sub(9.9) == "9.9x"
    assert fmt.sub(10) == "10x"
    assert fmt.sub(None) == "n/a"


def test_money_and_lot_and_est_gain():
    assert fmt.lot_cost(150, 100) == "₹15,000"
    assert fmt.est_gain(62, 100) == "+₹6,200"
    assert fmt.est_gain(-4.5, 100) == "-₹450"
    assert fmt.money(142_000) == "₹1.42L"
    assert fmt.money(120_000, signed=True) == "+₹1.2L"


def test_trend_arrows():
    assert fmt.trend("rising") == "↑"
    assert fmt.trend("falling") == "↓"
    assert fmt.trend("flat") == "→"
    assert fmt.trend("rising", legacy=True) == "↗"
    assert fmt.trend(None) == ""


def test_dates():
    assert fmt.date_heading("2026-10-05") == "5 Oct 2026"
    assert fmt.date_brief("2026-10-07") == "Wed 7 Oct"
    assert fmt.date_weekday("2026-10-08") == "Thu"


def test_board_label():
    assert fmt.board_label("MAIN") == "Main"
    assert fmt.board_label("SME") == "SME"
