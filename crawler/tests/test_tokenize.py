from crawler.learn.tokenize import tokenize


def test_lemmatizes_inflected_forms():
    toks = tokenize("знижки знижок знижкою")
    assert toks.count("знижка") >= 3  # усі форми → одна лема


def test_includes_bigrams():
    toks = tokenize("спеціальна ціна")
    assert "спеціальний ціна" in toks or "спеціальна ціна" in toks
