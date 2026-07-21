from crawler.discovery.lexicon import classify, OFFER_LEXICON, TARGET_LEXICON


def test_offer_known_vertical_reuses_seed_slug():
    assert ("Кафе/ресторани", "food") in classify("Знижка у нашому кафе", OFFER_LEXICON)


def test_offer_new_vertical_gets_new_slug():
    assert ("Автосервіс", "auto") in classify("Наш автосервіс і шиномонтаж", OFFER_LEXICON)


def test_offer_inflected_surface_form_matches():
    # word-start boundary keeps the inflected suffix ("барбершопі")
    assert ("Краса та догляд", "beauty") in classify("Знижка у барбершопі", OFFER_LEXICON)


def test_offer_no_match_returns_empty():
    assert classify("Просто новина без бізнесу", OFFER_LEXICON) == []


def test_offer_none_and_empty():
    assert classify(None, OFFER_LEXICON) == []
    assert classify("", OFFER_LEXICON) == []


def test_target_maps_military_to_ubd_slug():
    slugs = [s for _, s in classify("Знижка для військових і захисників", TARGET_LEXICON)]
    assert "ubd" in slugs


def test_target_maps_idp():
    slugs = [s for _, s in classify("Пропозиція для переселенців", TARGET_LEXICON)]
    assert "idp" in slugs


def test_classify_is_deduplicated():
    # two food stems in one text still yield a single (name, slug)
    got = classify("кафе і ресторан поруч", OFFER_LEXICON)
    assert got.count(("Кафе/ресторани", "food")) == 1


def test_target_lexicon_covers_dsns_and_police():
    got = {slug for _, slug in classify("знижка для рятувальників ДСНС", TARGET_LEXICON)}
    assert "dsns" in got
    got2 = {slug for _, slug in classify("акція для поліцейських", TARGET_LEXICON)}
    assert "police" in got2
