"""Manual veto tuning for the gazetteer generator.

Automatic veto (in build_gazetteer.is_common) flags a surface form marker-only
when pymorphy parses it as an adjective/verb — this catches adjectival
homograph town names (Вишневе→вишневий, Веселе, Берегове) while leaving
noun-only city names permissive. These sets tune the two cases the automatic
rule gets wrong:

- FORCE_MARKER: whole cities forced marker-only (their EVERY form needs a
  locality marker). Use for NOUN homographs the adjective/verb rule misses —
  names that are ordinary common nouns (Суми=сума pl., Буча=uproar,
  Бровари=brewers, Ізюм=raisins, Борщів=борщ gen.pl.).
- FORCE_PERMISSIVE: whole cities forced permissive, overriding the automatic
  adjective/verb veto. Use for adjectival-form oblast/major centres that are
  proper place-names, not common words (Хмельницький, Кропивницький, Миколаїв…).
"""

FORCE_MARKER: set[str] = {
    "Суми", "Буча", "Бровари", "Ізюм", "Борщів",
}

FORCE_PERMISSIVE: set[str] = {
    # 24 oblast centres + Kyiv + Sevastopol + two big cities, minus Суми/Рівне
    # (kept marker-only as noun/adjectival homographs — their oblique forms and
    # the м. locality marker still match).
    "Вінниця", "Луцьк", "Дніпро", "Донецьк", "Житомир", "Ужгород", "Запоріжжя",
    "Івано-Франківськ", "Київ", "Кропивницький", "Луганськ", "Львів", "Миколаїв",
    "Одеса", "Полтава", "Тернопіль", "Харків", "Херсон", "Хмельницький",
    "Черкаси", "Чернівці", "Чернігів", "Сімферополь", "Севастополь",
    "Кривий Ріг", "Маріуполь",
}
