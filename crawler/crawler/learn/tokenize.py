"""Офлайн-токенізація для майнера: леми укр. слів + біграми. Детерміновано за
піном pymorphy3-dicts-uk. Використовується ЛИШЕ в майнері, не в живому гейті."""

import re

import pymorphy3

_WORD = re.compile(r"[a-zа-яїієґ']{3,}", re.IGNORECASE)
_morph = pymorphy3.MorphAnalyzer(lang="uk")


def _lemma(word: str) -> str:
    parsed = _morph.parse(word.lower())
    return parsed[0].normal_form if parsed else word.lower()


def tokenize(text: str) -> list[str]:
    lemmas = [_lemma(w) for w in _WORD.findall(text or "")]
    bigrams = [f"{a} {b}" for a, b in zip(lemmas, lemmas[1:])]
    return lemmas + bigrams
