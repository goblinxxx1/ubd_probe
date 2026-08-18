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

# Slugs REUSE the DB target_categories seed slugs (resolver maps crawler slug -> DB id).
# `ubd` (combat-participant status) and `warrior` (serving military) are kept SEPARATE —
# sites write both, so each is classified to what the page actually says. `warrior-family`
# is intentionally NOT auto-classified: a substring stem cannot cleanly separate it from
# `warrior` («сім'ям військовослужбовців» matches both), and it is rare — the moderator
# refines those from the `warrior` tag.
TARGET_LEXICON = [
    ("УБД", "ubd", _compile((
        "убд", "учасник бойов", "бойових дій"))),
    ("Військовий", "warrior", _compile((
        "військов", ("воїн", r"(?!ськ)"), "захисник", ("зсу", r"(?!\w)"),
        "тероборон", "територіальн"))),
    ("Ветеран", "veteran", _compile(("ветеран",))),
    ("Особа з інвалідністю внаслідок війни", "war-disability", _compile((
        "інвалід", "інвалідніст"))),
    ("Сім'я загиблого", "fallen-family", _compile((
        "загибл", "полегл", ("вдов", r"(?!ол)")))),
    ("Внутрішньо переміщена особа", "idp", _compile((
        "переселен", ("впо", r"(?!\w)"), "переміщен"))),
    ("НГУ", "ngu", _compile((
        "нацгвард", ("нгу", r"(?!\w)")))),
    ("Працівник ДСНС", "dsns", _compile((
        "дснс", "рятувальник", "пожежник"))),
    ("Поліцейський", "police", _compile((
        "поліц", "нацполіц"))),
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
