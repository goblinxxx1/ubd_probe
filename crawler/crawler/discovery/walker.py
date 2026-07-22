"""Domain-depth expansion: turn a website homepage candidate into a small set of
promo-relevant page URLs (robots + sitemap + BFS fallback) under a per-domain politeness
layer. This module hosts the promo-URL filter; DomainWalker (added later) orchestrates."""

from urllib.parse import unquote, urlsplit

# Curated promo tokens (latin + cyrillic), matched against the lowercased, percent-decoded
# URL path. Same curation technique as query_grid.BRANDS.
_PROMO_URL_TOKENS: tuple[str, ...] = (
    "sale", "promo", "akci", "akcii", "aktsi", "znizhk", "znyzhk", "rozprodazh",
    "discount", "discounts", "offer", "offers", "deal", "deals", "black-friday",
    "blackfriday", "specialpropoz", "spec-propoz", "cyber-monday",
    "акці", "акция", "знижк", "розпродаж", "спецпропоз", "дисконт", "вигід",
)


def url_is_promo(url: str) -> bool:
    """True if the URL path contains any curated promo token (case/encoding insensitive)."""
    path = unquote(urlsplit(url or "").path).lower()
    return any(tok in path for tok in _PROMO_URL_TOKENS)
