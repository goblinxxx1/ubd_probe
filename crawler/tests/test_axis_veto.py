from crawler.learn.axis_veto import axis_veto_terms, is_axis_or_noise
from crawler.learn.tokenize import _lemma


def test_veto_contains_axis_and_noise_words():
    v = axis_veto_terms()
    assert _lemma("ветеран") in v          # audience axis
    assert _lemma("знижка") in v           # intent axis
    assert _lemma("київ") in v             # city axis
    assert _lemma("послуга") in v          # generic noise
    assert _lemma("україна") in v          # geo noise


def test_veto_excludes_real_services():
    v = axis_veto_terms()
    for svc in ("імплантація", "стоматологія", "окуляри", "протезування"):
        assert _lemma(svc) not in v, svc


def test_is_axis_or_noise():
    v = axis_veto_terms()
    assert is_axis_or_noise(_lemma("ветеран"), v) is True
    assert is_axis_or_noise("учасник дія", v) is True          # bigram, both vetoed
    assert is_axis_or_noise("протезування зубів", v) is False  # real service bigram
    assert is_axis_or_noise("стоматологія", v) is False
