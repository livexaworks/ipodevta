from bot import cards
from tests.conftest import TODAY


def _by_id(market, ipo_id):
    return next(i for i in market if i["ipo_id"] == ipo_id)


def test_mainboard_channel_card(market):
    html = cards.render_card(_by_id(market, "vishal-nirmiti-ipo"), today=TODAY, phase="channel", as_of="10:00")
    assert html == (
        "<b>📈 Vishal Nirmiti IPO GMP Today: ₹80 (+36.4%)</b>\n"
        "🏷 Mainboard IPO | 8 Oct 2026 | 🔴 Closes today\n"
        "\n"
        "💰 Price band: ₹210-220\n"
        "🎯 Est. listing: ₹300\n"
        "📊 Subscription (till yesterday): 2.4x\n"
        "QIB 3.1x | NII 1.2x | Retail 2x\n"
        "📅 Open 6 Oct | Close 8 Oct\n"
        "\n"
        "#VishalNirmitiIPO #IPOGMP #MainboardIPO #GMPToday #IPOSubscription\n"
        "\n"
        "🔔 Custom GMP alerts: @ipogmpalertsbot\n"
        "📢 Join: @ipogmpalerts | GMP is unofficial, not advice"
    )
    assert len(html) < 900
    assert "N/A" not in html and "None" not in html and "null" not in html
    assert "\n\n\n" not in html


def test_sme_bot_card(market):
    html = cards.render_card(_by_id(market, "eventions-sme-ipo"), today=TODAY, phase="bot", as_of="11:01")
    assert html == (
        "<b>📈 Eventions IPO GMP Today: ₹65 (+55.1%)</b>\n"
        "🏷 SME IPO | 8 Oct 2026 | 🟢 Opens today\n"
        "\n"
        "💰 Price: ₹118\n"
        "🎯 Est. listing: ₹183\n"
        "📅 Open 8 Oct | Close 12 Oct\n"
        "\n"
        "#EventionsIPO #IPOGMP #SMEIPO #GMPToday #IPOSubscription\n"
        "\n"
        "📢 Full daily list: @ipogmpalerts\n"
        "⚙️ Change filter: /filter"
    )
    assert "📊 Subscription" not in html  # null sub_total omitted
    assert len(html) < 900


def test_channel_opens_today_says_bidding_starts(market):
    html = cards.render_card(_by_id(market, "eventions-sme-ipo"), today=TODAY, phase="channel", as_of="10:00")
    assert "📊 Bidding starts today" in html
    assert "🔔 Custom GMP alerts: @ipogmpalertsbot" in html


def test_missing_fields_omits_lines(market):
    html = cards.render_card(_by_id(market, "no-gmp-yet-ipo"), today=TODAY, phase="bot", as_of="14:30")
    assert html.splitlines()[0] == "<b>📈 No GMP Yet Industries IPO</b>"
    assert "GMP Today" not in html.splitlines()[0]
    assert "💰 Price" not in html
    assert "Est. listing" not in html
    assert "📊 Subscription" not in html
    assert "N/A" not in html and "None" not in html and "not available" not in html
    assert "📢 Full daily list: @ipogmpalerts" in html
    assert len(html) < 900


def test_ampersand_is_escaped(market):
    html = cards.render_card(_by_id(market, "nityas-gems-jewellery-ipo"), today=TODAY, phase="bot", as_of="14:30")
    assert "Nityas Gems &amp; Jewellery" in html
    assert "#NityasGemsJewelleryIPO" in html


def test_every_card_under_900_and_has_hashtags(market):
    for ipo in market:
        for phase in ("channel", "bot"):
            html = cards.render_card(ipo, today=TODAY, phase=phase, as_of="10:00")
            assert len(html) < 900
            assert "#IPOGMP" in html
            assert "\n\n\n" not in html


def test_header_seo_title(market):
    open_now = [i for i in market if i["close_date"] >= TODAY]
    html = cards.render_header(open_now, today=TODAY, as_of="10:00")
    assert html.splitlines()[0] == "📊 <b>IPO GMP Today · 8 Oct 2026</b>"
    assert "<b>4</b> open · <b>1</b> closing today" in html
    assert "@ipogmpalerts" in html
    assert "#IPOGMP #GMPToday" in html


def test_no_match_and_keyboard():
    assert cards.render_no_match() == "🚫 No IPO passed your filters today. Stay out of the IPO market today."
    kb = cards.dm_keyboard(55)["inline_keyboard"]
    assert kb == [[
        {"text": "📢 Today's IPOs", "url": "https://t.me/ipogmpalerts/55"},
        {"text": "⚙️ Filters", "callback_data": "settings"},
    ]]
    assert cards.dm_keyboard(None)["inline_keyboard"][0][0]["url"] == "https://t.me/ipogmpalerts"
