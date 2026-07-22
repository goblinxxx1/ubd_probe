import pytest

from crawler.discovery.walker import url_is_promo


@pytest.mark.parametrize("url", [
    "https://shop.ua/sale",
    "https://shop.ua/promo/summer",
    "https://shop.ua/akcii",
    "https://shop.ua/akcii-znizhki",
    "https://shop.ua/rozprodazh",
    "https://shop.ua/discount",
    "https://shop.ua/offers/black-friday",
    "https://shop.ua/deals",
    "https://shop.ua/%D0%B0%D0%BA%D1%86%D1%96%D1%97",   # /акції percent-encoded
    "https://shop.ua/%D0%B7%D0%BD%D0%B8%D0%B6%D0%BA%D0%B8",  # /знижки
    "https://shop.ua/спецпропозиції",
])
def test_promo_urls_match(url):
    assert url_is_promo(url) is True


@pytest.mark.parametrize("url", [
    "https://shop.ua/",
    "https://shop.ua/product/12345",
    "https://shop.ua/blog/how-to",
    "https://shop.ua/about",
    "https://shop.ua/cart",
])
def test_non_promo_urls_do_not_match(url):
    assert url_is_promo(url) is False
