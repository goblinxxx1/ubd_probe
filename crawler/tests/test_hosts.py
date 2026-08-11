from crawler.util.hosts import bare_host, is_foreign_host


def test_foreign_cctld_hosts_are_foreign():
    # the reported bug: Belarusian sites
    assert is_foreign_host("https://brsm.by/") is True
    assert is_foreign_host("poodle.by") is True
    # other foreign country codes
    assert is_foreign_host("shop.ru") is True
    assert is_foreign_host("deal.pl") is True
    assert is_foreign_host("www.store.kz") is True
    assert is_foreign_host("x.md") is True


def test_ukrainian_hosts_are_not_foreign():
    assert is_foreign_host("shop.ua") is False
    assert is_foreign_host("https://rozetka.com.ua/x?y=1") is False
    assert is_foreign_host("sub.kyiv.ua") is False


def test_idn_foreign_cctlds_are_foreign():
    # the .рф leak: punycode ccTLD longer than 2 chars slipped the len==2 check
    assert is_foreign_host("https://xn--90aivcdt6dxbc.xn--p1ai/") is True  # .рф
    assert is_foreign_host("shop.xn--90ae") is True                        # .бг
    assert is_foreign_host("x.xn--90a3ac") is True                         # .срб


def test_ukrainian_idn_cctld_is_not_foreign():
    # .укр (xn--j1amh) is Ukraine's own IDN ccTLD — must stay allowed
    assert is_foreign_host("https://shop.xn--j1amh/") is False


def test_generic_gtlds_are_not_foreign():
    # legit UA businesses commonly sit on gTLDs, not .ua
    assert is_foreign_host("someshop.com") is False
    assert is_foreign_host("brand.net") is False
    assert is_foreign_host("cool.store") is False
    assert is_foreign_host("shop.online") is False


def test_repurposed_generic_cctlds_are_not_foreign():
    assert is_foreign_host("brand.co") is False
    assert is_foreign_host("app.io") is False
    assert is_foreign_host("hello.me") is False


def test_empty_or_hostless_is_not_foreign():
    assert is_foreign_host("") is False
    assert is_foreign_host(None) is False
    assert is_foreign_host("localhost") is False


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


def test_russian_city_subdomain_on_gtld_is_foreign():
    assert is_foreign_host("https://spb.boombate.com/zdorove/fitnes-kluby") is True
    assert is_foreign_host("msk.example.net") is True
    assert is_foreign_host("https://www.spb.foo.com/x") is True   # www stripped, spb kept
    assert is_foreign_host("ekb.shop.org") is True


def test_russian_heuristic_does_not_overblock():
    assert is_foreign_host("edclinic.com.ua") is False            # .ua host
    assert is_foreign_host("spb.example.com.ua") is False         # .ua wins even with spb
    assert is_foreign_host("shop.com") is False                   # legit gTLD, no ru subdomain
    assert is_foreign_host("mate.academy") is False
    assert is_foreign_host("sub.mate.academy") is False           # non-ru subdomain
    assert is_foreign_host("boombate.com") is False               # apex -> blocklist, not geo-gate
