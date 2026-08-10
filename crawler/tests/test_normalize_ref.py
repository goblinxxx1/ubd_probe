from crawler.discovery.passive import normalize_ref


def test_scheme_www_trailing_slash_still_collapse():
    a = normalize_ref("website", "https://www.shop.ua/deals/")
    b = normalize_ref("website", "http://shop.ua/deals")
    assert a == b == "shop.ua/deals"


def test_mobile_subdomain_collapses_to_desktop():
    a = normalize_ref("website", "https://m.lifecell.ua/announcements/956")
    b = normalize_ref("website", "https://lifecell.ua/announcements/956")
    assert a == b


def test_language_prefix_collapses():
    base = normalize_ref("website", "https://shop.ua/deals")
    assert normalize_ref("website", "https://shop.ua/en/deals") == base
    assert normalize_ref("website", "https://shop.ua/ru/deals") == base
    assert normalize_ref("website", "https://shop.ua/uk/deals") == base
    assert normalize_ref("website", "https://shop.ua/ua/deals") == base


def test_language_only_path_collapses_to_root():
    assert normalize_ref("website", "https://shop.ua/en/") == normalize_ref("website", "https://shop.ua")


def test_non_language_first_segment_preserved():
    # 'en'-like real segments must survive: only exact lang codes are stripped
    assert normalize_ref("website", "https://shop.ua/energy") == "shop.ua/energy"
    assert normalize_ref("website", "https://shop.ua/uadeals") == "shop.ua/uadeals"


def test_telegram_handle_not_touched_by_website_canonicalization():
    # lang/m. rules are website-only — a handle literally 'm.x' or 'en' must stay intact
    assert normalize_ref("telegram", "t.me/en") == "en"
    assert normalize_ref("instagram", "https://instagram.com/m.brand") == "m.brand"
