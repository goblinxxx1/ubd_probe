"""Pure, DB-free helpers for detecting duplicate promo offers across pages of one host.

Two crawler offers describe the SAME promo when one's discount magnitudes are a subset of
the other's AND their promo text is similar enough — even when worded differently on
different pages (apex, /pro-nas, /category). Text similarity is token-set Jaccard; the
threshold is deliberately conservative (doubt -> keep separate).
"""
import re

# Малий курований укр. стоп-лист: службові слова без промо-змісту.
_STOPWORDS = frozenset({
    "для", "на", "та", "і", "й", "з", "зі", "у", "в", "що", "як", "до",
    "від", "по", "за", "є", "а", "або", "при", "не", "the", "a",
})

_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


def normalize_tokens(text: str | None) -> frozenset[str]:
    """Lowercase, strip punctuation, drop stopwords -> a set of content tokens."""
    if not text:
        return frozenset()
    return frozenset(w for w in _TOKEN_RE.split(text.lower())
                     if w and w not in _STOPWORDS)


def text_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity of two token sets. Empty-vs-anything -> 0.0 (not a match)."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union


def discount_magnitudes(discounts, dt, dv) -> frozenset[tuple]:
    """Set of (discount_type, discount_value) across all of an offer's discounts.
    Falls back to the single top-level (dt, dv) when the discount list is empty."""
    mags = set()
    for d in discounts or []:
        t = getattr(d, "discount_type", None)
        if t is not None:
            mags.add((t, getattr(d, "discount_value", None)))
    if not mags and dt is not None:
        mags.add((dt, dv))
    return frozenset(mags)


def is_duplicate_promo(a_text, a_mags, b_text, b_mags, threshold: float) -> bool:
    """True when b already covers a's discounts (a_mags subset of b_mags) AND the two
    promo texts are similar enough. Subset because the candidate must cover everything
    the new offer proposes; text is the decisive guard against collapsing two genuinely
    different offers of the same percentage."""
    if not a_mags or not a_mags <= b_mags:
        return False
    return text_similarity(a_text, b_text) >= threshold
