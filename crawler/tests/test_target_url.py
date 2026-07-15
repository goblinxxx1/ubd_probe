from crawler.extract.heuristic import _pick_target


def test_pick_first_external_non_social():
    links = ["https://army.gov.ua/nav", "https://biz.example/deal?utm_source=x",
             "https://facebook.com/biz"]
    assert _pick_target(links, "https://army.gov.ua/page") == "https://biz.example/deal"


def test_none_when_only_same_host_or_social():
    links = ["https://army.gov.ua/x", "https://t.me/chan", "https://instagram.com/x"]
    assert _pick_target(links, "https://army.gov.ua/page") is None


def test_none_when_no_links():
    assert _pick_target([], "https://army.gov.ua/page") is None
