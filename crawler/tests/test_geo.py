from crawler.discovery.geo import find_city


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
