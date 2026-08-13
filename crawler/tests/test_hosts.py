from crawler.util.hosts import bare_host, is_foreign_host, is_ru_by_geo


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


# --- is_ru_by_geo: Russia/Belarus signal anywhere in the URL (ccTLD, subdomain,
#     OR path segment) -> the whole host must be blocked. ---

def test_ru_by_geo_path_segment_on_gtld():
    # the reported leak: /spb (Saint Petersburg) as a PATH segment on a gTLD host
    assert is_ru_by_geo("https://restoran.cafe/spb") is True
    assert is_ru_by_geo("https://restoran.cafe/spb/restaurant") is True
    assert is_ru_by_geo("https://x.com/city/msk/list") is True
    assert is_ru_by_geo("https://shop.org/ekb/") is True


def test_ru_by_geo_belarus_city_path_and_subdomain():
    assert is_ru_by_geo("https://x.com/minsk") is True            # BY city path
    assert is_ru_by_geo("https://gomel.example.com/x") is True    # BY city subdomain


def test_ru_by_geo_russian_city_subdomain():
    assert is_ru_by_geo("https://spb.boombate.com/x") is True
    assert is_ru_by_geo("msk.example.net") is True


def test_ru_by_geo_ru_by_cctlds():
    assert is_ru_by_geo("https://shop.ru") is True
    assert is_ru_by_geo("poodle.by") is True
    assert is_ru_by_geo("https://x.xn--p1ai/") is True            # .рф
    assert is_ru_by_geo("https://x.xn--90ais/") is True           # .бел


def test_ru_by_geo_whole_segment_only_no_substring():
    # /spbank contains "spb" but is not the segment "spb" -> must NOT match
    assert is_ru_by_geo("https://shop.com/spbank") is False
    assert is_ru_by_geo("https://shop.com/permanent") is False    # "perm" is a substring only


def test_ru_by_geo_ua_host_is_never_ru_by():
    # a confirmed-UA host (.ua) is Ukrainian; a coincidental /spb path must NOT block it
    assert is_ru_by_geo("https://shop.com.ua/spb") is False
    assert is_ru_by_geo("https://spb.example.com.ua/x") is False  # .ua wins over spb subdomain


def test_ru_by_geo_clean_urls_are_not_flagged():
    assert is_ru_by_geo("https://restoran.cafe/kyiv") is False
    assert is_ru_by_geo("https://shop.com/about") is False
    assert is_ru_by_geo("https://mate.academy/lviv") is False


def test_ru_by_geo_query_string_is_not_a_path_segment():
    # conservative: only PATH segments count, query params do not
    assert is_ru_by_geo("https://shop.com/list?city=spb") is False


def test_ru_by_geo_empty_or_none():
    assert is_ru_by_geo("") is False
    assert is_ru_by_geo(None) is False
