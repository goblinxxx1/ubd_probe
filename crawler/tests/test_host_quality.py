from crawler.discovery.host_quality import is_low_value_host, is_news_host, is_directory_page, DIRECTORY_HOST_SEEDS


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


def test_media_tld_is_news_host():
    assert is_news_host("moreliudei.media") is True
    assert is_news_host("https://suspilne.media/news/123") is True   # public broadcaster
    assert is_news_host("x.media") is True
    # existing token behavior still holds
    assert is_news_host("https://www.groza-news.info/x") is True
    assert is_news_host("kyiv.news") is True


def test_media_gate_does_not_block_cinemas_or_business():
    # cinemas are legitimate veteran-discount businesses (planetakino.ua is published)
    assert is_news_host("planetakino.ua") is False
    assert is_news_host("https://planetakino.ua/discounts") is False
    assert is_news_host("uaserials.com") is False       # .com — caught by seed, not this gate
    assert is_news_host("shop.ua") is False


_MYHELP = ("https://myhelp.com.ua/places/vinnytsia-language-school/services/"
           "znyzhka-dlia-uchasnykiv-boiovykh-dii-197164d0")


def test_directory_page_myhelp_seed_host_and_title():
    assert is_directory_page(_MYHELP, "Знижка ... для ... Vinnytsia Language School | MY Help")


def test_directory_page_url_pattern_non_seed_host():
    # non-seed host but clear listing-entry path + brand title
    url = "https://katalog-znyzhok.ua/company/kavarnya-lviv/offers/minus-15"
    assert is_directory_page(url, "Кав'ярня Львів | Каталог знижок")


def test_directory_page_false_on_first_party_business():
    # a real business's own discount page: no listing path, no brand-suffix title
    assert not is_directory_page("https://kavarnya-lviv.com.ua/aktsiyi",
                                 "Акції — Кав'ярня Львів")


def test_directory_page_false_when_title_has_no_brand_separator():
    # seed host but title without ' | ' → still treat as directory via seed host?
    # NO: require BOTH signals, so a bare seed-host page with no brand title is not matched here
    assert not is_directory_page(_MYHELP, "Vinnytsia Language School")
