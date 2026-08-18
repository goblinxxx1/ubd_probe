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
    # NB: bare "special" removed — matched 'type-specialists'/doctor pages (each carries the
    # site-wide banner), flooding the queue with dupes. Specific forms ('specialna',
    # 'specialpropoz', 'spec-propoz', 'spec-cina') above/here still match.
    "utsinka", "bonus", "cashback", "specialna", "spec-cina",
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
# Complementary free SERVICES — a free consultation/delivery is NOT a price discount
# (web: it's a supplementary service). Masked out before the FREE check so
# «безкоштовна консультація» alone isn't an offer, while «безкоштовне навчання/вхід/
# освіта» (a genuine free offer) still counts.
FREE_SERVICE = re.compile(
    r"(?:безкоштовн|безплатн|безоплатн)\w*\s+(?:консультаці|доставк|замір|підбір|оцінк|парковк)",
    re.IGNORECASE)
# Price RANGE "від X ₴ до Y ₴" — a shop catalog's from-to span, never a single fixed
# discount. Gates the FIXED branch so «Одяг ЗСУ від 125 ₴ до 9156 ₴» isn't read as a
# «125 грн» offer. A single «від X грн» (no «до») is a real discount and NOT matched here.
PRICE_RANGE = re.compile(
    r"від\s*\d[\d\s]*(?:₴|грн|гривень|uah)?\s*до\s*\d[\d\s]*\s*(?:₴|грн|гривень|uah)",
    re.IGNORECASE)

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


_WORD_START = "/-_.+ "


def _seg_hit(path: str, tokens) -> bool:
    """True iff any token starts a word/segment in `path` (preceded by start-of-path or one
    of / - _ . + space). Word-start stem matching — the match the module docstring promises —
    so a token never fires mid-word: 'aktsi' (акція) can't match inside 'atraktsionah'
    (атракціон). Tokens may carry their own hyphens (e.g. 'national-guard')."""
    for t in tokens:
        i = path.find(t)
        while i != -1:
            if i == 0 or path[i - 1] in _WORD_START:
                return True
            i = path.find(t, i + 1)
    return False


def url_is_promo(url: str) -> bool:
    path = unquote(urlsplit(url or "").path).lower()
    return _seg_hit(path, SEED_URL_TOKENS)


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
    # лояльність / бонусна програма ("bonus" already in SEED_URL_TOKENS).
    # bare "loyal" stem covers /loyal/ (canonical page), /loyalty/, /loyalnist/…
    "loyal", "club",
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
    # russian-language mirror pages — the aggressor's language, never crawled. The `/ru/`
    # language segment (with both slashes) never collides with a Ukrainian slug that merely
    # contains the letters "ru" mid-word.
    "/ru/",
    # reviews / testimonials — customer opinions about service quality, practically never a
    # real offer (a review quoting a past discount was a false-positive source).
    "review", "otzyv", "vidhuk", "vidguk", "testimonial", "відгук", "отзыв",
    # photo galleries — imagery, never carry offers.
    "photogallery", "gallery", "galereya", "галере", "фотогалер",
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
    if _seg_hit(path, INCLUDE_TOKENS):
        return True
    if anchor_text and any(a in anchor_text.lower() for a in INCLUDE_ANCHORS):
        return True
    return False


def seed_is_target(url: str) -> bool:
    """A seed/candidate URL is fetched-as-target iff it is the domain root or a target."""
    return unquote(urlsplit(url or "").path) in ("", "/") or page_is_target(url)
