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
    assert pl.url_is_promo("https://shop.ua/sale/winter")
    assert pl.url_is_promo("https://shop.ua/%D0%B0%D0%BA%D1%86%D1%96%D1%97")  # акції
    assert not pl.url_is_promo("https://shop.ua/about")


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
