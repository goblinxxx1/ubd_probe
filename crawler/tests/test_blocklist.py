from crawler.discovery.blocklist import is_blocked_host


def test_exact_media_host_blocked():
    assert is_blocked_host("nv.ua")


def test_subdomain_suffix_blocked():
    assert is_blocked_host("biz.nv.ua")
    assert is_blocked_host("ua.depositphotos.com")


def test_gov_ua_tld_blocked():
    assert is_blocked_host("zakon.rada.gov.ua")
    assert is_blocked_host("nszu.gov.ua")


def test_www_prefix_ignored():
    assert is_blocked_host("www.tiktok.com")


def test_business_host_not_blocked():
    assert not is_blocked_host("yourburger.example")


def test_none_and_empty_not_blocked():
    assert not is_blocked_host(None)
    assert not is_blocked_host("")


def test_lookalike_not_blocked():
    # must not match "nv.ua" as a bare substring
    assert not is_blocked_host("mynv.ua")


def test_observed_live_leaks_blocked():
    # domains caught leaking as fake providers during live active-search runs
    assert is_blocked_host("www.dnipro.media")
    assert is_blocked_host("fakty.com.ua")
    assert is_blocked_host("blog.ipay.ua")
    assert is_blocked_host("ukr.net")


def test_aggregator_portal_blocked():
    # aggregators/directories/NGO write-ups are not the actual provider
    assert is_blocked_host("veteranam.info")
    assert is_blocked_host("www.veteranam.info")
    assert is_blocked_host("engage.org.ua")
    assert is_blocked_host("goncharenkocentre.com.ua")


def test_is_blocked_telegram_handle():
    from crawler.discovery.blocklist import is_blocked_telegram
    assert is_blocked_telegram("https://t.me/nau_info", "КАІ • Корисна інфа") is True
    assert is_blocked_telegram("t.me/nau_info", None) is True
    assert is_blocked_telegram("@nau_info", None) is True


def test_is_blocked_telegram_news_name():
    from crawler.discovery.blocklist import is_blocked_telegram
    assert is_blocked_telegram("t.me/somechan", "Львівські новини") is True
    assert is_blocked_telegram("t.me/uni_kai", "Університет — інфо для студентів") is True


def test_is_blocked_telegram_allows_business():
    from crawler.discovery.blocklist import is_blocked_telegram
    assert is_blocked_telegram("t.me/kava_lviv", "Кав'ярня Львів") is False


def test_business_info_handle_not_blocked():
    from crawler.discovery.blocklist import is_blocked_telegram
    # "*_info" is a common legit business-handle convention — must NOT be blocked
    assert is_blocked_telegram("t.me/salon_info", "Салон краси") is False
    assert is_blocked_telegram("t.me/pizza_lviv_info", "Піца Львів") is False
    # but an explicit blocklisted handle and strong news terms still block
    assert is_blocked_telegram("t.me/nau_info", None) is True
    assert is_blocked_telegram("t.me/x", "Львівські новини") is True
