import pytest
from pydantic import ValidationError

from app.schemas.offer import OfferCreate


def _base(**over):
    data = dict(type="discount", title="T", provider="P",
                discount_type="percent", discount_value="10")
    data.update(over)
    return data


def test_valid_urls_accepted():
    o = OfferCreate(**_base(site_url="https://ex.com", article_url="http://ex.com/a"))
    assert o.site_url == "https://ex.com"
    assert o.article_url == "http://ex.com/a"


def test_empty_urls_become_none():
    o = OfferCreate(**_base(site_url="", article_url=None))
    assert o.site_url is None
    assert o.article_url is None


def test_non_url_rejected():
    with pytest.raises(ValidationError):
        OfferCreate(**_base(site_url="not-a-url"))
