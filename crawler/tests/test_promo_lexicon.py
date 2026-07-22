import json
from crawler.discovery import promo_lexicon as pl


def test_seed_offer_triggers_match_current_gate():
    # ті самі 8 стемів, що були в heuristic._OFFER_TRIGGERS
    for stem in ("знижк", "акці", "промокод", "безкоштов", "безплатн", "діє до",
                 "спецпропоз", "розпродаж"):
        assert stem in pl.SEED_OFFER_TRIGGERS


def test_url_is_promo_matches_tokens():
    assert pl.url_is_promo("https://shop.ua/sale/winter")
    assert pl.url_is_promo("https://shop.ua/%D0%B0%D0%BA%D1%86%D1%96%D1%97")  # акції
    assert not pl.url_is_promo("https://shop.ua/about")


def test_learned_terms_augment_offer_triggers(tmp_path):
    pl.reload_learned(None)
    assert "уцінк" not in pl.offer_triggers()
    f = tmp_path / "learned.json"
    f.write_text(json.dumps([{"term": "уцінк"}]), encoding="utf-8")
    pl.reload_learned(str(f))
    assert "уцінк" in pl.offer_triggers()
    pl.reload_learned(None)  # reset for other tests
    assert "уцінк" not in pl.offer_triggers()
