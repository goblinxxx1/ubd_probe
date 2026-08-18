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


def test_target_maps_serving_military_to_warrior_slug():
    slugs = [s for _, s in classify("Знижка для військових і захисників", TARGET_LEXICON)]
    assert "warrior" in slugs           # serving military -> warrior, its own audience
    assert "ubd" not in slugs           # NOT the UBD (combat-participant status) slug


def test_target_ubd_is_explicit_status_only():
    slugs = [s for _, s in classify("Знижка для УБД та учасників бойових дій", TARGET_LEXICON)]
    assert "ubd" in slugs


def test_target_ngu_national_guard():
    slugs = [s for _, s in classify("Акція для нацгвардійців НГУ", TARGET_LEXICON)]
    assert "ngu" in slugs


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


# --- precision: stems must not fire on word-initial homographs ---

def test_zsu_acronym_matches_but_not_zsuv():
    assert "warrior" in {s for _, s in classify("знижка для ЗСУ", TARGET_LEXICON)}
    assert "warrior" not in {s for _, s in classify("зсув грунту та зсунути меблі", TARGET_LEXICON)}


def test_vpo_acronym_matches_but_not_vporyadkuvaty():
    assert "idp" in {s for _, s in classify("пільга для ВПО", TARGET_LEXICON)}
    assert "idp" not in {s for _, s in classify("треба впорядкувати та впоратися", TARGET_LEXICON)}


def test_vdova_matches_but_not_vdovolennia():
    assert "fallen-family" in {s for _, s in classify("спеціальна пропозиція вдовам", TARGET_LEXICON)}
    assert "fallen-family" not in {s for _, s in classify("повне вдоволення клієнта", TARGET_LEXICON)}


def test_voin_matches_but_not_voinskyi_oblik():
    assert "warrior" in {s for _, s in classify("знижка воїнам", TARGET_LEXICON)}
    assert classify("воїнський облік у місті", TARGET_LEXICON) == []


def test_vsu_russian_abbrev_is_not_an_audience():
    # ВСУ is the russian-language abbreviation — must not be a target token at all
    assert classify("акція для ВСУ", TARGET_LEXICON) == []


def test_kafe_matches_but_not_kafedra():
    assert "food" in {s for _, s in classify("знижка у кафе", OFFER_LEXICON)}
    assert "food" not in {s for _, s in classify("кафедра університету", OFFER_LEXICON)}


def test_sushi_matches_but_not_sushinnia():
    assert "food" in {s for _, s in classify("замовити суші", OFFER_LEXICON)}
    assert "food" not in {s for _, s in classify("сушіння білизни надворі", OFFER_LEXICON)}
