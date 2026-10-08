from bot import cards
from tests.conftest import TODAY


def _by_id(market, ipo_id):
    return next(i for i in market if i["ipo_id"] == ipo_id)


def test_closing_today_card_bot(market):
    html = cards.render_card(_by_id(market, "vishal-nirmiti-ipo"), today=TODAY, phase="bot", as_of="14:31")
    assert html == (
        "<b>Vishal Nirmiti</b>\n"
        "Mainboard · 🔴 Closes today\n"
        "📅 Open 6 Oct → Close 8 Oct\n"
        "💰 Price ₹220\n"
        "📈 GMP ₹80 (+36.4%)\n"
        "📊 Subscription 2.4x (live 2:31 PM)"
    )


def test_channel_card_says_till_yesterday(market):
    html = cards.render_card(_by_id(market, "nityas-gems-jewellery-ipo"), today=TODAY, phase="channel", as_of="09:30")
    assert html == (
        "<b>Nityas Gems &amp; Jewellery</b>\n"
        "Mainboard\n"
        "📅 Open 7 Oct → Close 9 Oct\n"
        "💰 Price ₹75\n"
        "📈 GMP ₹3 (+4%)\n"
        "📊 Subscription 0.7x (till yesterday)"
    )


def test_opens_today_card(market):
    sme = _by_id(market, "eventions-sme-ipo")
    channel = cards.render_card(sme, today=TODAY, phase="channel", as_of="09:30")
    assert channel.splitlines()[1] == "SME · 🟢 Opens today"
    assert channel.splitlines()[-1] == "📊 Bidding starts today"
    bot = cards.render_card(sme, today=TODAY, phase="bot", as_of="14:30")
    assert bot.splitlines()[-1] == "📊 Subscription not available yet"


def test_missing_price_and_gmp(market):
    html = cards.render_card(_by_id(market, "no-gmp-yet-ipo"), today=TODAY, phase="bot", as_of="14:30")
    assert "💰 Price not announced" in html
    assert "📈 GMP not available" in html


def test_name_is_first_line_and_bold(market):
    for ipo in market:
        first = cards.render_card(ipo, today=TODAY, phase="bot", as_of="14:30").splitlines()[0]
        assert first.startswith("<b>") and first.endswith("</b>")


def test_header_counts(market):
    open_now = [i for i in market if i["close_date"] >= TODAY]
    html = cards.render_header(open_now, today=TODAY, as_of="09:30")
    assert html.splitlines()[:2] == ["📊 <b>IPO Market · Thu 8 Oct</b>", "4 open · 1 closing today"]
    assert "9:30 AM IST" in html


def test_no_match_and_keyboard():
    assert cards.render_no_match() == "🚫 No IPO passed your filters today. Stay out of the IPO market today."
    kb = cards.dm_keyboard(55)["inline_keyboard"]
    assert kb == [[
        {"text": "📢 Today's IPOs", "url": "https://t.me/ipodevta/55"},
        {"text": "⚙️ Filters", "callback_data": "settings"},
    ]]
    assert cards.dm_keyboard(None)["inline_keyboard"][0][0]["url"] == "https://t.me/ipodevta"
