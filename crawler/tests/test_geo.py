from crawler.discovery.geo import find_city, is_online


def test_nominative_match():
    assert find_city("Знижка діє у місті Львів") == "Львів"


def test_locative_inflection():
    assert find_city("Наша кав'ярня у Києві") == "Київ"


def test_genitive_inflection():
    assert find_city("Акція для мешканців Одеси") == "Одеса"


def test_multiword_city():
    assert find_city("м. Біла Церква, вул. Шевченка") == "Біла Церква"


def test_no_city_returns_none():
    assert find_city("Знижка для військових") is None
    assert find_city(None) is None
    assert find_city("") is None


def test_word_boundary_avoids_false_match():
    # "рівні" (level) must not match the city Рівне
    assert find_city("сервіс на рівні найкращих") is None


def test_online_detected():
    assert is_online("Знижки в нашому інтернет-магазині для УБД")
    assert is_online("Працюємо онлайн по всій Україні")


def test_online_not_detected():
    assert not is_online("Знижка у кафе на вулиці")
    assert not is_online(None)


def test_kyiv_agglomeration_towns():
    assert find_city("м. Вишневе, вул. Київська 1") == "Вишневе"
    assert find_city("наш заклад в Ірпені") == "Ірпінь"
    assert find_city("м. Бровари, просп. Незалежності") == "Бровари"


def test_homograph_towns_need_locality_prefix():
    # bare common-word homographs must NOT be read as cities
    assert find_city("знижка на вишневе морозиво для військових") is None
    assert find_city("місцеві бровари варять пиво") is None
    assert find_city("зчинилася буча навколо цін") is None


def test_homograph_towns_match_with_prefix():
    assert find_city("м. Вишневе, вул. Київська 1") == "Вишневе"
    assert find_city("смт Буча, центр") == "Буча"
    assert find_city("у місто Бровари") == "Бровари"
