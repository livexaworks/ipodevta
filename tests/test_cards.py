from bot import cards
from tests.conftest import TODAY


def _by_id(market, ipo_id):
    return next(i for i in market if i["ipo_id"] == ipo_id)


def test_closing_today_card_bot(market):
    html = cards.render_card(_by_id(market, "vishal-nirmiti-ipo"), today=TODAY, phase="bot", as_of="11:01")
    assert html == (
        "<b>Vishal Nirmiti</b>\n"
        "\n"
        "<b>Mainboard</b> · 🔴 Closes today\n"
        "\n"
        "📅 Open <b>6 Oct</b> → Close <b>8 Oct</b>\n"
        "\n"
        "💰 Price <b>₹220</b>\n"
        "📈 GMP <b>₹80</b> (<b>+36.4%</b>)\n"
        "📊 Subscription <b>2.4x</b> (live 11:01 AM)\n"
        "\n"
        '<a href="https://t.me/ipodevta">@ipodevta</a>'
    )


def test_channel_card_says_till_yesterday(market):
    html = cards.render_card(_by_id(market, "nityas-gems-jewellery-ipo"), today=TODAY, phase="channel", as_of="10:00")
    assert html == (
        "<b>Nityas Gems &amp; Jewellery</b>\n"
        "\n"
        "<b>Mainboard</b>\n"
        "\n"
        "📅 Open <b>7 Oct</b> → Close <b>9 Oct</b>\n"
        "\n"
        "💰 Price <b>₹75</b>\n"
        "📈 GMP <b>₹3</b> (<b>+4%</b>)\n"
        "📊 Subscription <b>0.7x</b> (till yesterday)\n"
        "\n"
        '<a href="https://t.me/ipodevta">@ipodevta</a>'
    )


def test_opens_today_card(market):
    sme = _by_id(market, "eventions-sme-ipo")
    channel = cards.render_card(sme, today=TODAY, phase="channel", as_of="10:00")
    assert channel.splitlines()[2] == "<b>SME</b> · 🟢 Opens today"
    assert "📊 Bidding <b>starts today</b>" in channel
    assert channel.endswith('@ipodevta</a>')
    bot = cards.render_card(sme, today=TODAY, phase="bot", as_of="14:30")
    assert "📊 Subscription <b>not available yet</b>" in bot


def test_missing_price_and_gmp(market):
    html = cards.render_card(_by_id(market, "no-gmp-yet-ipo"), today=TODAY, phase="bot", as_of="14:30")
    assert "💰 Price <b>not announced</b>" in html
    assert "📈 GMP <b>not available</b>" in html


def test_name_is_first_line_and_bold(market):
    for ipo in market:
        first = cards.render_card(ipo, today=TODAY, phase="bot", as_of="14:30").splitlines()[0]
        assert first.startswith("<b>") and first.endswith("</b>")


def test_every_card_ends_with_channel_tag(market):
    for ipo in market:
        html = cards.render_card(ipo, today=TODAY, phase="channel", as_of="10:00")
        assert html.endswith('<a href="https://t.me/ipodevta">@ipodevta</a>')


def test_header_counts(market):
    open_now = [i for i in market if i["close_date"] >= TODAY]
    html = cards.render_header(open_now, today=TODAY, as_of="10:00")
    assert html.splitlines()[0] == "📊 <b>IPO Market · Thu 8 Oct</b>"
    assert "<b>4</b> open · <b>1</b> closing today" in html
    assert "10:00 AM IST" in html
    assert html.endswith('<a href="https://t.me/ipodevta">@ipodevta</a>')


def test_no_match_and_keyboard():
    assert cards.render_no_match() == "🚫 No IPO passed your filters today. Stay out of the IPO market today."
    kb = cards.dm_keyboard(55)["inline_keyboard"]
    assert kb == [[
        {"text": "📢 Today's IPOs", "url": "https://t.me/ipodevta/55"},
        {"text": "⚙️ Filters", "callback_data": "settings"},
    ]]
    assert cards.dm_keyboard(None)["inline_keyboard"][0][0]["url"] == "https://t.me/ipodevta"
