"""Єдиний source-of-truth промо/relevance-словника: курований SEED + навчений
LEARNED (у репо порожній, наповнюється audit CLI). Живий матчинг — regex word-start
стем, детермінований (як geo.py/lexicon.py)."""

import json
import re
from urllib.parse import unquote, urlsplit

# --- SEED: точна копія теперішніх розкиданих токенів (без розширення на цьому кроці) ---
SEED_OFFER_TRIGGERS: tuple[str, ...] = (
    "знижк", "акці", "промокод", "безкоштов", "безплатн", "діє до",
    "спецпропоз", "розпродаж",
)
SEED_URL_TOKENS: tuple[str, ...] = (
    "sale", "promo", "akci", "akcii", "aktsi", "znizhk", "znyzhk", "rozprodazh",
    "discount", "discounts", "offer", "offers", "deal", "deals", "black-friday",
    "blackfriday", "specialpropoz", "spec-propoz", "cyber-monday",
    "акці", "акция", "знижк", "розпродаж", "спецпропоз", "дисконт", "вигід",
)

DISCOUNT_CTX = re.compile(
    r"знижк|акці|розпродаж|спецпропоз|промокод|економ|вигід|-\s*\d", re.IGNORECASE)
FREE = re.compile(r"безкоштов|безплатн|\bfree\b", re.IGNORECASE)
INCREASE = re.compile(
    r"зростан|подорожч|підвищенн\w*\s+варт|дорожч|буде\s+[\d\s]+грн", re.IGNORECASE)

_learned_terms: tuple[str, ...] = ()


def reload_learned(path: str | None) -> None:
    global _learned_terms
    if not path:
        _learned_terms = ()
        return
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        _learned_terms = tuple(
            e["term"] for e in data if isinstance(e, dict) and e.get("term"))
    except (OSError, ValueError, KeyError, TypeError):
        _learned_terms = ()


def offer_triggers() -> tuple[str, ...]:
    return SEED_OFFER_TRIGGERS + _learned_terms


def url_is_promo(url: str) -> bool:
    path = unquote(urlsplit(url or "").path).lower()
    return any(tok in path for tok in SEED_URL_TOKENS)
