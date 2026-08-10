"""Єдиний source-of-truth промо/relevance-словника: курований SEED + навчений
LEARNED (у репо порожній, наповнюється audit CLI). Живий матчинг — regex word-start
стем, детермінований (як geo.py/lexicon.py)."""

import json
import re
from urllib.parse import unquote, urlsplit

# --- SEED: ядро (точна копія теперішніх розкиданих токенів) + курований розширений лексикон ---
SEED_OFFER_TRIGGERS: tuple[str, ...] = (
    # --- ядро (як було) ---
    "знижк", "акці", "промокод", "безкоштов", "безплатн", "безоплатн", "діє до",
    "спецпропоз", "розпродаж",
    # --- розширення (курований маркетинг-лексикон) ---
    "уцінк", "ліквідац", "бонус", "кешбек", "подарунок", "тільки сьогодні",
    "супер ціна", "супер-ціна", "гаряч пропозиц", "друга за пів ціни",
    "спеціальна ціна", "спец ціна", "вигідна пропозиц",
)
SEED_URL_TOKENS: tuple[str, ...] = (
    # --- ядро (ТОЧНО як у walker, 26) ---
    "promo", "akci", "akcii", "aktsi", "znizhk", "znyzhk", "rozprodazh",
    "discount", "discounts", "offer", "offers", "deal", "deals", "black-friday",
    "blackfriday", "specialpropoz", "spec-propoz", "cyber-monday",
    "акці", "акция", "знижк", "розпродаж", "спецпропоз", "дисконт", "вигід",
    # --- розширення ---
    # NB: "sale"/"hot" removed — over-matched product slugs (chereviki-«sale»wa brand,
    # termos-«hot»-and-cold), stealing the walker's page_cap from real veteran/info pages.
    "utsinka", "bonus", "cashback", "special", "specialna", "spec-cina",
)

DISCOUNT_CTX = re.compile(
    r"знижк|акці|розпродаж|спецпропоз|промокод|економ|вигід|-\s*\d", re.IGNORECASE)
FREE = re.compile(
    r"безкоштов|безплатн|безоплатн|\bfree\b|"
    r"\b[ву]\s+подарунок|\bу\s+дарунок|"      # кваліфіковані форми; голе "подарунок" над-матчить
    r"даром|задарма|(?<!\d)0\s*(?:грн|₴)",
    re.IGNORECASE)
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


# --- page-type targeting (superset of promo; drives DomainWalker page selection) ---

# High-yield info/veteran page-type slugs (promo slugs come from SEED_URL_TOKENS).
_PAGE_TYPE_TOKENS: tuple[str, ...] = (
    # для військових / ветеранів
    "viysk", "viyskov", "viyskovosluzhb", "military", "army", "zsu",
    "veteran", "zahisnik", "zakhisnik", "defender",
    # інші сили безпеки/оборони: ТрО, поліція, ДСНС, Нацгвардія (НГУ), УБД
    "teroboron", "police", "policiy", "dsns", "nacgvard", "natsgvard",
    "national-guard", "nationalguard", "ubd",
    "теробор", "поліці", "поліц", "дснс", "нацгвард", "гвард", "убд", "бойов",
    # контакти
    "kontakt", "contact",
    # доставка й оплата
    "dostavka", "oplata", "delivery", "payment", "shipping",
    # про нас
    "pro-nas", "pro_nas", "pronas", "pro-kompaniyu", "about", "o-nas", "o_nas",
    # лояльність / бонусна програма ("bonus" already in SEED_URL_TOKENS)
    "loyaln", "loyalty", "club",
    # faq / корисна інформація
    "faq", "pytannya", "pitannya", "korysn", "korisn", "useful",
    # кирилиця (decoded percent-encoded paths)
    "військов", "ветеран", "захисник", "контакт", "доставка", "оплата",
    "про-нас", "лояльн", "бонус", "корисн", "питання",
)

INCLUDE_TOKENS: tuple[str, ...] = SEED_URL_TOKENS + _PAGE_TYPE_TOKENS

# Low-yield page types — never fetch as target, never traverse into (BFS).
EXCLUDE_TOKENS: tuple[str, ...] = (
    "/product", "/tovar", "/goods", "/item", "/p/",
    "cart", "koshyk", "checkout", "/order",
    "account", "login", "signin", "/register", "cabinet", "kabinet",
    "/profile", "wishlist",
    "blog", "news", "novyny", "/search", "poshuk", "filter", "/tag", "privacy", "cookie",
)

# Link-anchor-text signals (lowercased substrings) for opaque URLs.
INCLUDE_ANCHORS: tuple[str, ...] = (
    "військов", "ветеран", "зсу", "захисник", "убд",
    "територіальна оборона", "поліці", "дснс", "національна гвардія",
    "нацгвардія", "бойових дій",
    "знижка для військовослужбовц", "контакт", "доставка", "оплата",
    "про нас", "про компанію", "лояльн", "бонусна програма", "клуб",
    "корисна інформація", "питання", "акці", "знижк",
)


def is_excluded(url: str) -> bool:
    path = unquote(urlsplit(url or "").path).lower()
    return any(t in path for t in EXCLUDE_TOKENS)


def page_is_target(url: str, anchor_text: str | None = None) -> bool:
    if is_excluded(url):
        return False                                    # EXCLUDE wins
    path = unquote(urlsplit(url or "").path).lower()
    if any(t in path for t in INCLUDE_TOKENS):
        return True
    if anchor_text and any(a in anchor_text.lower() for a in INCLUDE_ANCHORS):
        return True
    return False


def seed_is_target(url: str) -> bool:
    """A seed/candidate URL is fetched-as-target iff it is the domain root or a target."""
    return unquote(urlsplit(url or "").path) in ("", "/") or page_is_target(url)
