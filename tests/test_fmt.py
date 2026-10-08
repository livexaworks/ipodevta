from bot import fmt


def test_esc():
    assert fmt.esc("A&B <Beta>") == "A&amp;B &lt;Beta&gt;"
    assert fmt.esc(None) == ""


def test_display_name():
    assert fmt.display_name("ACME SOLAR LIMITED") == "Acme Solar"
    assert fmt.display_name("fx parts ltd.") == "FX Parts"


def test_board_label():
    assert fmt.board_label("MAIN") == "Mainboard"
    assert fmt.board_label("SME") == "SME"


def test_rupees():
    assert fmt.rupees(220) == "₹220"
    assert fmt.rupees(1250.5) == "₹1,250.5"
    assert fmt.rupees(-4) == "-₹4"
    assert fmt.rupees(None) is None


def test_pct():
    assert fmt.pct(36.36) == "+36.4%"
    assert fmt.pct(4.0) == "+4%"
    assert fmt.pct(-2.54) == "-2.5%"
    assert fmt.pct(0) == "0%"
    assert fmt.pct(None) is None


def test_sub():
    assert fmt.sub(0.69) == "0.7x"
    assert fmt.sub(2.0) == "2x"
    assert fmt.sub(142.4) == "142x"
    assert fmt.sub(None) is None


def test_dates_and_time():
    assert fmt.date_short("2026-09-30") == "30 Sep"
    assert fmt.date_short(None) is None
    assert fmt.date_long("2026-10-08") == "Thu 8 Oct"
    assert fmt.time_12h("14:30") == "2:30 PM"
    assert fmt.time_12h("09:05") == "9:05 AM"
    assert fmt.time_12h("12:00") == "12:00 PM"
