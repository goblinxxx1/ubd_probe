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


# Generic hub/listing terminal slugs (UA + neutral-English only; no Russian forms). A page
# whose LAST path segment is one of these is a storefront/index page, not a specific offer.
_HUB_SLUGS = frozenset({
    "promotions", "promotion", "aktsiyi", "aktsii", "akciyi", "akcia", "akciji",
    "znizhki", "znyzhky", "discounts", "sale", "sales", "offers",
    "propozicii", "propozycii", "category", "categories", "catalog", "katalog",
    "about", "about-us", "pro-nas", "pronas", "main", "home", "index",
})


def _path_only(canon: str) -> str:
    """Drop the query string from a canonicalize_target_url() key -> 'host/path'."""
    return canon.split("?", 1)[0]


def is_hub_page(incoming_canon: str, peer_canon: str) -> bool:
    """True when the incoming offer page is a hub/listing page relative to a peer offer:
    the bare apex (host, no path), a strict URL-parent of the peer, or a page whose terminal
    path segment is a generic-hub slug. Pure string logic over canonicalize_target_url()
    keys ('host/path[?query]'). Only the TERMINAL segment is matched against _HUB_SLUGS, so a
    deep offer page with a hub word mid-path (e.g. /promotion/znyzhka-viyskovm) is not a hub."""
    if not incoming_canon:
        return False
    inc = _path_only(incoming_canon)
    peer = _path_only(peer_canon)
    if "/" not in inc:                       # apex: host only, no path segment
        return True
    if peer.startswith(inc + "/"):           # incoming is a strict path-ancestor of the peer
        return True
    return inc.rsplit("/", 1)[-1] in _HUB_SLUGS   # terminal segment is a generic hub word
