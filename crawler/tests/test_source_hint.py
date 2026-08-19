from types import SimpleNamespace

from crawler.discovery.source_hint import business_domains_from_page


def _it(text="", links=None):
    return SimpleNamespace(text=text, links=links or [])


def test_email_domain_differing_from_host_is_hinted():
    items = [_it("Бронювання: reservation.hg@optimahotels.com.ua")]
    assert business_domains_from_page(items, "visitlviv.com.ua") == {"optimahotels.com.ua"}


def test_mailto_link_is_read():
    items = [_it(links=["mailto:info@shop.com.ua", "https://x/y"])]
    assert business_domains_from_page(items, "afisha.ua") == {"shop.com.ua"}


def test_freemail_and_same_host_and_foreign_excluded():
    items = [_it("a@gmail.com b@visitlviv.com.ua c@shop.ru d@biz.ua")]
    assert business_domains_from_page(items, "visitlviv.com.ua") == {"biz.ua"}


def test_no_email_is_empty():
    assert business_domains_from_page([_it("нема пошти тут")], "x.ua") == set()
