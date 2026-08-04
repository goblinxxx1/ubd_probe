from crawler.learn.tokenize import service_terms, tokenize


def test_lemmatizes_inflected_forms():
    toks = tokenize("знижки знижок знижкою")
    assert toks.count("знижка") >= 3  # усі форми → одна лема


def test_includes_bigrams():
    toks = tokenize("спеціальна ціна")
    assert "спеціальний ціна" in toks or "спеціальна ціна" in toks


def test_service_terms_keeps_nouns_drops_verbs_and_adjectives():
    out = service_terms("купуйте дешеву каву")   # verb, adjective, noun
    assert "кава" in out
    assert "купуйте" not in out and "дешевий" not in out


def test_service_terms_noun_bigrams():
    out = service_terms("автомийка самообслуговування")
    assert "автомийка" in out and "самообслуговування" in out
    assert "автомийка самообслуговування" in out   # noun-noun bigram


def test_service_terms_empty_is_empty():
    assert service_terms("") == []
