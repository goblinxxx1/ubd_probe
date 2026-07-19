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
