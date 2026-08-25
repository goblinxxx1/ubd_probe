import json
from crawler.discovery import promo_lexicon as pl


def test_seed_offer_triggers_match_current_gate():
    # ті самі 8 стемів, що були в heuristic._OFFER_TRIGGERS
    for stem in ("знижк", "акці", "промокод", "безкоштов", "безплатн", "діє до",
                 "спецпропоз", "розпродаж"):
        assert stem in pl.SEED_OFFER_TRIGGERS


def test_expanded_offer_triggers_present():
    for stem in ("уцінк", "ліквідац", "бонус", "кешбек", "подарунок",
                 "тільки сьогодні", "супер ціна", "гаряч пропозиц",
                 "друга за пів ціни", "спеціальна ціна"):
        assert stem in pl.SEED_OFFER_TRIGGERS


def test_new_trigger_makes_offer_recognisable():
    from crawler.extract.base import CategoryIndex, get_extractor
    from crawler.models import RawItem
    cats = CategoryIndex(target=[{"id": 10, "name": "Ветеран", "slug": "veteran"}], offer=[])
    ex = get_extractor("heuristic")
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Уцінка на зимову колекцію для ветеранів")
    assert ex.extract(item, "Shop", cats) is not None


def test_url_is_promo_matches_tokens():
    assert pl.url_is_promo("https://shop.ua/promo/winter")
    assert pl.url_is_promo("https://shop.ua/%D0%B0%D0%BA%D1%86%D1%96%D1%97")  # акції
    assert not pl.url_is_promo("https://shop.ua/about")
    assert not pl.url_is_promo("https://shop.ua/chereviki-salewa")  # 'sale' removed: brand-safe


def test_learned_terms_augment_offer_triggers(tmp_path):
    # "рібейт" — синтетичний плейсхолдер, свідомо відсутній у SEED (на відміну від
    # "уцінк", який тепер курований SEED-термін; див. test_expanded_offer_triggers_present)
    pl.reload_learned(None)
    assert "рібейт" not in pl.offer_triggers()
    f = tmp_path / "learned.json"
    f.write_text(json.dumps([{"term": "рібейт"}]), encoding="utf-8")
    pl.reload_learned(str(f))
    assert "рібейт" in pl.offer_triggers()
    pl.reload_learned(None)  # reset for other tests
    assert "рібейт" not in pl.offer_triggers()


from crawler.discovery import promo_lexicon as _pl


def test_discount_ctx_excludes_shareholder_homograph():
    assert _pl.DISCOUNT_CTX.search("консультація юриста по акціонерні товариства") is None
    assert _pl.DISCOUNT_CTX.search("права акціонера") is None
    # real promo words still match
    assert _pl.DISCOUNT_CTX.search("акція для військових") is not None
    assert _pl.DISCOUNT_CTX.search("акційна ціна на все") is not None
    assert _pl.DISCOUNT_CTX.search("наші акції та знижки") is not None
    assert _pl.DISCOUNT_CTX.search("знижка 20%") is not None


def test_discount_ctx_recognizes_typographic_and_word_forms():
    # типографські тире — реальні сайти рендерять – / − , не ASCII-дефіс
    assert _pl.DISCOUNT_CTX.search("військовим –15%") is not None   # en dash U+2013
    assert _pl.DISCOUNT_CTX.search("військовим −15%") is not None   # minus U+2212
    assert _pl.DISCOUNT_CTX.search("військовим -15%") is not None   # ASCII (регресія)
    # словоформа «мінус» і додаткові знижкові маркери
    assert _pl.DISCOUNT_CTX.search("ветеранам мінус 15%") is not None
    assert _pl.DISCOUNT_CTX.search("кешбек 10% військовим") is not None
    assert _pl.DISCOUNT_CTX.search("спеціальна ціна для ветеранів") is not None
    assert _pl.DISCOUNT_CTX.search("спеціальні ціни для військових") is not None
    # СВІДОМО не матчимо (шумовий клас)
    assert _pl.DISCOUNT_CTX.search("військовим —15%") is None       # em dash U+2014 (буліт)
    assert _pl.DISCOUNT_CTX.search("комісія 15% від суми") is None  # голе % без контексту
    assert _pl.DISCOUNT_CTX.search("акційний набір 1+1 військовим") is not None  # «акці» вже ловить
    # наявні негативи-омографи лишаються негативами
    assert _pl.DISCOUNT_CTX.search("права акціонера") is None


def test_is_catalog_page_matches_generic_catalog_categories():
    assert pl.is_catalog_page("https://epicentrk.ua/ua/shop/razdvizhnye-sistemy-dlya-dverey/")
    assert pl.is_catalog_page("https://shop.ua/catalog/dveri")
    assert pl.is_catalog_page("https://shop.ua/category/mebli")
    assert pl.is_catalog_page("https://shop.ua/collection/summer")
    assert pl.is_catalog_page("https://shop.ua/c/12345")


def test_is_catalog_page_false_for_promo_and_info_and_veteran():
    # promo/veteran pages must NOT read as generic catalog (BFS target-check runs first,
    # but the raw predicate should also be false where there is no /shop//catalog token)
    assert not pl.is_catalog_page("https://epicentrk.ua/ua/actions/floor-promo.html")
    assert not pl.is_catalog_page("https://shop.ua/veteranam")
    assert not pl.is_catalog_page("https://shop.ua/akcii")
    assert not pl.is_catalog_page("https://shop.ua/")
    assert not pl.is_catalog_page("")
