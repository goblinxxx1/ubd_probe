"""Offline curated lexicon: map keyword stems to canonical categories.

Precision over recall. Stems are matched at a word-start boundary (no
end-boundary, so inflected suffixes survive) — the same technique as geo.py.
Known verticals REUSE the DB seed slugs; new verticals get fresh slugs and are
lazily created in the DB by the crawler's resolver."""

import re


def _compile(stems):
    r"""Word-start stems. An item may be a bare stem, or a (stem, tail) pair where
    `tail` is raw regex appended after the escaped stem — used to block word-initial
    homographs (e.g. ("зсу", r"(?!\w)") matches ЗСУ but not «зсув»; ("вдов", r"(?!ол)")
    matches «вдова» but not «вдоволення») while inflected suffixes still survive."""
    out = []
    for s in stems:
        stem, tail = s if isinstance(s, tuple) else (s, "")
        out.append(re.compile(r"(?<!\w)" + re.escape(stem) + tail))
    return out


# (name, slug, compiled stem patterns). Order is stable => classify() is deterministic.
OFFER_LEXICON = [
    ("Розваги", "rozvahy", _compile((
        "розваг", "квест", "боулінг", "кінотеатр", "атракціон", "караоке",
        "більярд", "лазертаг"))),
    ("Музеї", "museums", _compile((
        "музе", "галере", "виставк", "експозиц"))),
    ("Кафе/ресторани", "food", _compile((
        "кав'ярн", ("кафе", r"(?!др)"), "ресторан", "бариста", "піцер",
        ("суші", r"(?!нн)"), "паб ",
        "їдальн", "бістро", "кондитер", "пекарн"))),
    ("Спорт", "sport", _compile((
        "спорт", "фітнес", "тренаж", "качалк", "єдиноборст", "басейн", "йога",
        "кросфіт"))),
    ("Освіта", "education", _compile((
        "освіт", "курси", "навчанн", "тренінг", "репетитор", "автошкол",
        "вебінар"))),
    ("Транспорт", "transport", _compile((
        "транспорт", "таксі", "каршеринг", "переїзд", "доставк"))),
    ("Медицина", "medicine", _compile((
        "клінік", "медцентр", "медичн", "діагностик", "реабілітац",
        "офтальмолог"))),
    ("Краса та догляд", "beauty", _compile((
        "перукар", "барбершоп", "манікюр", "педикюр", "косметолог", "епіляц",
        "візаж"))),
    ("Автосервіс", "auto", _compile((
        "автосервіс", "шиномонтаж", "автомийк", "запчастин", "ремонт авто"))),
    ("Аптека", "pharmacy", _compile(("аптек", "фармац"))),
    ("Стоматологія", "dentistry", _compile(("стоматолог", "дантист", "зубн"))),
    ("Одяг та взуття", "clothing", _compile((
        "одяг", "взутт", "ательє", "кросівк"))),
    ("Квіти", "flowers", _compile(("квіт", "флорист", "букет"))),
    ("Готелі та відпочинок", "hotels", _compile((
        "готель", "хостел", "база відпочинк", "санатор", "екскурс"))),
    ("Книги та канцтовари", "books", _compile(("книгарн", "канцтовар"))),
    ("Електроніка", "electronics", _compile((
        "електронік", "гаджет", "смартфон", "ноутбук"))),
    ("Юридичні послуги", "legal", _compile((
        "юридичн", "адвокат", "нотаріус", "юрист"))),
    ("Оптика", "optics", _compile(("оптик", "окуляр", "лінз"))),
]

TARGET_LEXICON = [
    ("УБД", "ubd", _compile((
        "убд", "учасник бойов", "бойових дій", ("воїн", r"(?!ськ)"), "військов",
        "захисник", ("зсу", r"(?!\w)"), "тероборон"))),
    ("Ветеран", "veteran", _compile(("ветеран",))),
    ("Особа з інвалідністю внаслідок війни", "war-disability", _compile((
        "інвалід", "інвалідніст"))),
    ("Сім'я загиблого", "fallen-family", _compile((
        "загибл", "полегл", "родин загибл", ("вдов", r"(?!ол)")))),
    ("Внутрішньо переміщена особа", "idp", _compile((
        "переселен", ("впо", r"(?!\w)"), "переміщен особ"))),
    ("Працівник ДСНС", "dsns", _compile((
        "дснс", "рятувальник", "надзвичайних ситуац", "пожежник"))),
    ("Поліцейський", "police", _compile((
        "поліц", "нацполіц", "національної поліції"))),
]


def classify(text, lexicon):
    if not text:
        return []
    low = text.lower()
    out = []
    for name, slug, patterns in lexicon:
        if any(p.search(low) for p in patterns):
            out.append((name, slug))
    return out
