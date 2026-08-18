from crawler.discovery.host_quality import is_low_value_host, is_news_host


def test_news_hosts_flagged():
    assert is_news_host("https://www.groza-news.info/korinnyj-uzhgorodecz/") is True
    assert is_news_host("rivnenews.com.ua") is True          # <city>news concatenated
    assert is_news_host("novyny.live") is True
    assert is_news_host("epravda.com.ua") is True            # pravda
    assert is_news_host("kyiv.news") is True                 # .news tld label


def test_news_gate_leaves_business_hosts():
    for h in ("edclinic.com.ua", "smartlab.ua", "mate.academy",
              "https://rozetka.com.ua/", "comfy.ua", "silpo.ua"):
        assert is_news_host(h) is False
    assert is_news_host("") is False
    assert is_news_host(None) is False


def test_institutional_tlds_are_low_value():
    # foreign gov/military/international bodies — never a UA discount business
    assert is_low_value_host("https://www.va.gov/") is True            # US veterans affairs
    assert is_low_value_host("militaryonesource.mil") is True          # US military
    assert is_low_value_host("https://www.wipo.int/x") is True         # WIPO
    assert is_low_value_host("hudoc.echr.coe.int") is True             # ECHR


def test_ua_educational_and_gov_second_level_are_low_value():
    # reference/lectures/registers, not offers
    assert is_low_value_host("https://nangu.edu.ua/books/") is True
    assert is_low_value_host("legalclinic.nlu.edu.ua") is True
    assert is_low_value_host("https://diia.gov.ua/") is True


def test_global_platforms_are_low_value():
    assert is_low_value_host("https://www.reddit.com/r/x") is True
    assert is_low_value_host("steamcommunity.com") is True
    assert is_low_value_host("commons.wikimedia.org") is True
    assert is_low_value_host("https://fliphtml5.com/abc/") is True
    assert is_low_value_host("ru.trip.com") is True


def test_real_ua_businesses_are_not_low_value():
    assert is_low_value_host("https://rozetka.com.ua/") is False
    assert is_low_value_host("comfy.ua") is False
    assert is_low_value_host("silpo.ua") is False
    assert is_low_value_host("https://about.pumb.ua/") is False
    assert is_low_value_host("aurora.ua") is False


def test_empty_or_hostless_is_not_low_value():
    assert is_low_value_host("") is False
    assert is_low_value_host(None) is False
