from bot import hashtags


def test_company_hashtag_real_style_names():
    assert hashtags.company_hashtag("Shree Ram Twistex Ltd") == "#ShreeRamTwistexIPO"
    assert hashtags.company_hashtag("Nityas Gems & Jewellery Limited") == "#NityasGemsJewelleryIPO"
    assert hashtags.company_hashtag("R.K.Fashion Accessories") == "#RKFashionAccessoriesIPO"
    assert hashtags.company_hashtag("HD Fire Protect (India) Ltd.") == "#HDFireProtectIndiaIPO"
    assert hashtags.company_hashtag("3B Films Ltd") == "#3BFilmsIPO"
    assert hashtags.company_hashtag("Acme Solar IPO Ltd") == "#AcmeSolarIPO"


def test_hashtag_line_mainboard_and_sme():
    main = hashtags.hashtag_line({"name": "Vishal Nirmiti", "board": "MAIN"})
    assert main == "#VishalNirmitiIPO #IPOGMP #MainboardIPO #GMPToday #IPOSubscription"
    sme = hashtags.hashtag_line({"name": "Eventions", "board": "SME"})
    assert sme == "#EventionsIPO #IPOGMP #SMEIPO #GMPToday #IPOSubscription"
