from crawler.util.hosts import bare_host


def test_scheme_url_to_bare_host():
    assert bare_host("https://shop.ua/deal?x=1") == "shop.ua"


def test_strips_www():
    assert bare_host("https://www.shop.ua/") == "shop.ua"


def test_strips_port_and_userinfo():
    assert bare_host("http://user:pw@www.shop.ua:8080/x") == "shop.ua"


def test_scheme_less_input_resolves_to_host():
    assert bare_host("shop.ua") == "shop.ua"
    assert bare_host("www.shop.ua") == "shop.ua"


def test_empty_and_none_return_empty_string():
    assert bare_host("") == ""
    assert bare_host(None) == ""
    assert bare_host("   ") == ""


def test_subdomain_preserved():
    assert bare_host("https://sub.shop.ua/p") == "sub.shop.ua"
