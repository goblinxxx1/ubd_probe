"""Offline gazetteer: map Ukrainian city surface forms to a canonical name.

Precision over recall — only curated cities match, via explicit surface forms
(nominative + common oblique cases) with word boundaries, so inflected mentions
are caught without stemming collisions (e.g. `рівні` != `Рівне`)."""

import re

# canonical -> lowercase surface forms (nominative + common oblique cases)
_CITIES = {
    "Київ": ("київ", "києві", "києва"),
    "Львів": ("львів", "львові", "львова"),
    "Харків": ("харків", "харкові", "харкова"),
    "Одеса": ("одеса", "одесі", "одеси"),
    "Дніпро": ("дніпро", "дніпрі", "дніпра"),
    "Запоріжжя": ("запоріжжя", "запоріжжі"),
    "Вінниця": ("вінниця", "вінниці"),
    "Полтава": ("полтава", "полтаві", "полтави"),
    "Чернігів": ("чернігів", "чернігові", "чернігова"),
    "Черкаси": ("черкаси", "черкасах", "черкас"),
    "Житомир": ("житомир", "житомирі", "житомира"),
    "Суми": ("суми", "сумах"),
    "Рівне": ("рівне", "рівному", "рівного"),
    "Івано-Франківськ": ("івано-франківськ", "івано-франківську", "івано-франківська"),
    "Тернопіль": ("тернопіль", "тернополі", "тернополя"),
    "Луцьк": ("луцьк", "луцьку", "луцька"),
    "Ужгород": ("ужгород", "ужгороді", "ужгорода"),
    "Хмельницький": ("хмельницький", "хмельницькому"),
    "Чернівці": ("чернівці", "чернівцях"),
    "Кропивницький": ("кропивницький", "кропивницькому"),
    "Миколаїв": ("миколаїв", "миколаєві", "миколаєва"),
    "Херсон": ("херсон", "херсоні", "херсона"),
    "Маріуполь": ("маріуполь", "маріуполі", "маріуполя"),
    "Краматорськ": ("краматорськ", "краматорську", "краматорська"),
    "Біла Церква": ("біла церква", "білій церкві", "білої церкви"),
}

# (form, canonical), longest form first so specific forms win
_FORMS = sorted(
    ((form, city) for city, forms in _CITIES.items() for form in forms),
    key=lambda fc: len(fc[0]), reverse=True,
)
_PATTERNS = [(re.compile(r"(?<!\w)" + re.escape(f) + r"(?!\w)"), c) for f, c in _FORMS]


def find_city(text: str | None) -> str | None:
    if not text:
        return None
    low = text.lower()
    for pat, city in _PATTERNS:
        if pat.search(low):
            return city
    return None


_ONLINE = re.compile(r"(?<!\w)(онлайн|інтернет[-\s]?магазин)\w*", re.IGNORECASE)


def is_online(text: str | None) -> bool:
    """Online-only signal — used as a location fallback when no city is found."""
    return bool(text and _ONLINE.search(text))
