from app.crud.dedup import is_hub_page


def test_apex_is_hub():
    # bare host, no path -> hub regardless of peer
    assert is_hub_page("smartlab.ua", "smartlab.ua/deep/offer") is True


def test_apex_with_query_is_hub():
    # a query string carries no literal '/', so apex detection still holds
    assert is_hub_page("smartlab.ua?ref=x", "smartlab.ua/deep") is True


def test_url_parent_is_hub():
    # incoming is a strict path-ancestor of the peer (whiteclinic case)
    assert is_hub_page("whiteclinic.ua/promotions",
                       "whiteclinic.ua/promotions/znyzhka-10-dlja-uchasnykiv") is True


def test_generic_slug_is_hub():
    # terminal segment is a curated hub word (mebelmarket / m2fit / tovpollar cases)
    assert is_hub_page("mebelmarket.ua/promotions", "mebelmarket.ua/promotion/znyzhka") is True
    assert is_hub_page("m2fit.com.ua/about", "m2fit.com.ua/veteran") is True
    assert is_hub_page("tovpollar.org/category/aktsii", "tovpollar.org/znyzhky-zsu") is True


def test_only_terminal_segment_counts():
    # a deep offer page whose MIDDLE segment is a hub word is NOT a hub
    assert is_hub_page("mebelmarket.ua/promotion/znyzhka-viyskovm",
                       "mebelmarket.ua/promotions") is False


def test_descriptive_offer_slug_is_not_hub():
    assert is_hub_page("smartlab.ua/deep/znyzhka-10-dlja-uchasnykiv",
                       "smartlab.ua/aktsii") is False


def test_siblings_are_not_hub():
    # two deep sibling pages -> neither is a hub of the other (regression guard)
    assert is_hub_page("smartlab.ua/one", "smartlab.ua/two") is False


def test_empty_incoming_is_not_hub():
    assert is_hub_page("", "smartlab.ua/deep") is False
