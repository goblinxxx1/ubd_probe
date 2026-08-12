from crawler.extract.base import CategoryIndex, get_extractor
from crawler.models import RawItem


CATS = CategoryIndex(
    target=[{"id": 10, "name": "Ветеран", "slug": "veteran"}],
    offer=[{"id": 20, "name": "Кафе/ресторани", "slug": "food"}],
)


def _item(text):
    return RawItem(source_id=1, platform="website", key="k", text=text)


def test_non_offer_returns_none():
    ex = get_extractor("heuristic")
    assert ex.extract(_item("Просто новина без пропозицій"), "Shop", CATS) is None


def test_percent_discount_parsed():
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Знижка 20% для ветеранів у нашому кафе"), "Кафе Львів", CATS)
    assert cand is not None
    assert cand.discount_type == "percent"
    assert cand.discount_value == "20"
    assert cand.provider == "Кафе Львів"
    assert 10 in cand.target_category_ids                       # "ветеран" → veteran
    assert ("Кафе/ресторани", "food") in cand.offer_category_matches   # "кафе" → food
    assert cand.offer_category_ids == []                        # ids filled later by resolver
    assert len(cand.content_hash) == 64


def test_free_offer_parsed():
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Безкоштовно для військових!"), "Музей", CATS)
    assert cand is not None
    assert cand.discount_type == "free"
    assert cand.discount_value is None


def test_location_from_structured_locality():
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Знижка 20% для ветеранів у кафе", locality="Львів")
    cand = get_extractor("heuristic").extract(it, "Кафе", CATS)
    assert cand.locations == ["Львів"]


def test_location_from_gazetteer_fallback():
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для ветеранів у нашому кафе в Одесі"), "Кафе", CATS)
    assert cand.locations == ["Одеса"]


def test_location_none_when_absent():
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для ветеранів"), "Кафе", CATS)
    assert cand.locations == []


def test_location_online_fallback():
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для ветеранів у нашому інтернет-магазині"), "Shop", CATS)
    assert cand.locations == ["Онлайн"]


def test_title_is_concise_headline():
    text = ("Знижка 20% для ветеранів. Пропозиція діє у нашому кафе протягом "
            "усього місяця на всі напої та десерти без винятку сьогодні.")
    cand = get_extractor("heuristic").extract(_item(text), "Кафе", CATS)
    assert cand.title == "Знижка 20% для ветеранів."
    assert cand.body == text  # description keeps the full text


def test_local_llm_is_hook_only():
    import pytest
    with pytest.raises(NotImplementedError):
        get_extractor("local_llm")


def test_offer_category_from_site_name_context():
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Знижка 20% для ветеранів", site_name="Барбершоп Резервіст")
    cand = get_extractor("heuristic").extract(it, "Shop", CATS)
    assert ("Краса та догляд", "beauty") in cand.offer_category_matches


def test_target_from_military_keyword_resolves_existing_only():
    # "військових" → ubd, but CATS has no ubd row → no id resolved (no creation)
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для військових"), "Shop", CATS)
    assert cand.target_category_ids == []


def test_offer_without_target_audience_is_skipped():
    ex = get_extractor("heuristic")
    # real discount phrase, but no "для кого" audience signal -> not a UBD offer
    assert ex.extract(_item("Знижка 20% на все у нашому магазині"), "Shop", CATS) is None


def test_offer_for_dsns_passes_gate():
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Знижка 15% для рятувальників ДСНС"), "Магазин", CATS)
    assert cand is not None
    assert cand.discount_type == "percent"


def test_price_increase_without_discount_returns_none():
    ex = get_extractor("heuristic")
    # has a structural trigger ("діє до") + audience ("ветеранів") but it's a price HIKE
    txt = "Подорожчання проїзду для ветеранів діє до 15 липня, буде 544 грн"
    assert ex.extract(_item(txt), "Новини", CATS) is None


def test_bare_percentage_is_not_an_offer():
    ex = get_extractor("heuristic")
    # a percentage + audience word, but NO discount trigger word at all
    assert ex.extract(_item("18% студентів-ветеранів мають знижений тариф"), "Новини", CATS) is None


def test_percent_word_vidsotkiv_parsed():
    # Discounts written in words ("20 відсотків") must parse as percent, not fall to free.
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20 відсотків для ветеранів у нашому магазині"), "Shop", CATS)
    assert cand.discount_type == "percent"
    assert cand.discount_value == "20"


def test_percent_word_protsentiv_parsed():
    cand = get_extractor("heuristic").extract(
        _item("Акція: 15 процентів знижки для військових"), "Shop", CATS)
    assert cand.discount_type == "percent"
    assert cand.discount_value == "15"


def test_sale_percent_still_parsed():
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Розпродаж 50% для військових"), "Shop", CATS)
    assert cand is not None
    assert cand.discount_type == "percent"
    assert cand.discount_value == "50"


from crawler.discovery import promo_lexicon as pl
from crawler.extract.heuristic import HeuristicExtractor
from crawler.extract.base import CategoryIndex
from crawler.models import RawItem


def test_free_synonyms_detected():
    for phrase in ["безоплатне обслуговування", "у подарунок кава",
                   "в подарунок десерт", "каву даром", "0 грн за вхід"]:
        assert pl.FREE.search(phrase.lower()), phrase


def test_bare_podarunok_not_matched():
    # "купіть подарунок" must NOT be read as a free offer
    assert not pl.FREE.search("купіть подарунок другу")


def test_extractor_free_synonym_gives_free_type():
    # text contains "ветеран" -> classify() yields target slug "veteran"; "безоплатне" -> free
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Безоплатне обслуговування для ветеранів у нашому центрі")
    res = ex.extract(item, "Center", CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[]))
    assert res is not None
    assert res.discount_type == "free"


def test_extractor_hryven_full_form_gives_fixed():
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 200 гривень для ветеранів на послуги")
    res = ex.extract(item, "Shop", CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[]))
    assert res is not None
    assert res.discount_type == "fixed"
    assert res.discount_value == "200"


def test_round_hryvnia_price_not_misread_as_free():
    # "200 грн" must NOT be read as FREE (0-substring false-positive); it's a fixed discount
    assert not pl.FREE.search("знижка 200 грн")
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 200 грн для ветеранів на послуги")
    res = ex.extract(item, "Shop", CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[]))
    assert res is not None
    assert res.discount_type == "fixed" and res.discount_value == "200"


def test_standalone_zero_hryvnia_still_free():
    assert pl.FREE.search("вхід 0 грн")


def _target_cats():
    return CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[])


def _no_discount_offer_item():
    # offer trigger ("знижки") + target ("ветеранів") but NO concrete %/грн/free
    return RawItem(source_id=1, platform="website", key="k",
                   text="Знижки для ветеранів у нашому магазині завжди актуальні")


def test_gate_drops_no_discount_when_required():
    ex = HeuristicExtractor(require_discount=True)
    assert ex.extract(_no_discount_offer_item(), "Shop", _target_cats()) is None


def test_gate_keeps_offer_with_discount_when_required():
    ex = HeuristicExtractor(require_discount=True)
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 15% для ветеранів у нашому магазині")
    res = ex.extract(item, "Shop", _target_cats())
    assert res is not None and res.discount_type == "percent"


def test_default_permissive_keeps_no_discount_offer():
    ex = HeuristicExtractor()  # class-default require_discount=False -> byte-eq to pre-track
    assert ex.extract(_no_discount_offer_item(), "Shop", _target_cats()) is not None


def test_get_extractor_passes_require_discount():
    from crawler.extract.base import get_extractor
    ex = get_extractor("heuristic", require_discount=True)
    assert ex._require_discount is True
    assert get_extractor("heuristic")._require_discount is False


def test_title_uses_site_tagline_when_present():
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 15% для ветеранів у нашому магазині",
                   site_tagline="Магазин тактичного спорядження")
    res = ex.extract(item, "P", CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[]))
    assert res is not None
    assert res.title == "Магазин тактичного спорядження"


def test_title_falls_back_to_promo_when_no_tagline():
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 15% для ветеранів у нашому магазині")
    res = ex.extract(item, "P", CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[]))
    assert res is not None
    assert res.title == "Знижка 15% для ветеранів у нашому магазині"


def test_free_rejected_when_audience_only_in_provider_not_text():
    from crawler.extract.heuristic import HeuristicExtractor
    from crawler.models import RawItem
    ex = HeuristicExtractor(require_discount=True)
    # free word in the block text, but the audience token is only in provider/site_name,
    # not in the block prose -> free must NOT count -> no discount -> None (require_discount).
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Безкоштовна доставка по всій Україні. Умови доставки та оплати.",
                 site_name="Магазин для ветеранів")
    # free word in text, NO audience/percent/fixed in text; audience only in site_name/provider
    assert ex.extract(it, "Магазин для ветеранів", CATS) is None


def test_fixed_with_context_still_emitted():
    ex = HeuristicExtractor(require_discount=True)
    res = ex.extract(_item("Знижка 500 грн для ветеранів на послуги"), "Shop", CATS)
    assert res is not None
    assert res.discount_type == "fixed" and res.discount_value == "500"


def test_fixed_minus_sign_style_emitted():
    ex = HeuristicExtractor(require_discount=True)
    res = ex.extract(_item("Розпродаж -500 грн для військових"), "Shop", CATS)
    assert res is not None
    assert res.discount_type == "fixed" and res.discount_value == "500"


def test_fixed_price_without_context_dropped_when_required():
    # trigger "тільки сьогодні" (not DISCOUNT_CTX) + price 2000 грн + audience -> a PRICE, not a discount
    ex = HeuristicExtractor(require_discount=True)
    res = ex.extract(_item("Тільки сьогодні! Куртка 2000 грн для ветеранів"), "Shop", CATS)
    assert res is None


def test_fixed_price_without_context_permissive_emits_no_discount():
    # permissive default: offer still emitted, but the bare price is no longer a fixed discount
    ex = HeuristicExtractor()  # require_discount=False
    res = ex.extract(_item("Тільки сьогодні! Куртка 2000 грн для ветеранів"), "Shop", CATS)
    assert res is not None
    assert res.discount_type is None


def test_free_kept_when_audience_in_same_block_text():
    from crawler.extract.base import get_extractor
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Безкоштовні протези ветеранам у нашій клініці"), "Клініка", CATS)
    assert cand is not None and cand.discount_type == "free"


def test_free_fails_but_percent_with_context_still_extracts():
    from crawler.extract.base import get_extractor
    ex = get_extractor("heuristic")
    # generic free (no audience token in the block text) + a real percent discount; audience
    # comes from the provider (offer-level gate over blob) -> free fails, falls through to percent.
    from crawler.models import RawItem
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Безкоштовна доставка. Знижка 20% на все у нашому магазині.")
    cand = ex.extract(it, "Магазин для військових", CATS)
    assert cand is not None and cand.discount_type == "percent" and cand.discount_value == "20"


def test_content_hash_ignores_site_tagline():
    ex = HeuristicExtractor()
    cats = CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[])
    text = "Знижка 15% для ветеранів у нашому магазині"
    a = ex.extract(RawItem(source_id=1, platform="website", key="k", text=text,
                           site_tagline="Опис А"), "P", cats)
    b = ex.extract(RawItem(source_id=1, platform="website", key="k", text=text,
                           site_tagline="Опис Б"), "P", cats)
    assert a.content_hash == b.content_hash          # hash decoupled from tagline (no churn)
    assert a.title == "Опис А" and b.title == "Опис Б"


def test_provider_uses_site_name_when_present():
    from crawler.extract.base import get_extractor
    from crawler.models import RawItem
    ex = get_extractor("heuristic")
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Знижка 20% для ветеранів", site_name="Гастро-бар Угловой")
    cand = ex.extract(it, "uglovoy.com.ua", CATS)   # host passed as provider param
    assert cand is not None and cand.provider == "Гастро-бар Угловой"


def test_provider_falls_back_to_host_without_site_name():
    from crawler.extract.base import get_extractor
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Знижка 20% для ветеранів"), "uglovoy.com.ua", CATS)  # no site_name
    assert cand is not None and cand.provider == "uglovoy.com.ua"


def test_content_hash_unchanged_when_only_display_provider_differs():
    from crawler.extract.base import get_extractor
    from crawler.models import RawItem
    ex = get_extractor("heuristic")
    text = "Знижка 20% для ветеранів"
    with_name = ex.extract(RawItem(source_id=1, platform="website", key="k",
                                   text=text, site_name="Гастро-бар Угловой"), "uglovoy.com.ua", CATS)
    no_name = ex.extract(_item(text), "uglovoy.com.ua", CATS)
    assert with_name.content_hash == no_name.content_hash   # hash on host, not display name


def test_provider_prefers_logo_alt_over_site_name():
    # logo <img alt> is the cleanest business name — it wins over og:site_name/title.
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Знижка 20% для ветеранів", site_name="og-name",
                 logo_alt="Terra Incognita")
    cand = get_extractor("heuristic").extract(it, "arg-provider", CATS)
    assert cand.provider == "Terra Incognita"


def test_provider_falls_back_to_site_name_without_logo_alt():
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Знижка 20% для ветеранів", site_name="og-name")
    cand = get_extractor("heuristic").extract(it, "arg-provider", CATS)
    assert cand.provider == "og-name"
