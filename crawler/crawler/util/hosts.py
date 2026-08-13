"""Єдиний нормалізатор голого хоста для всього краулера.

Приймає як повний URL ("https://www.shop.ua:8080/x"), так і вже голий хост
("shop.ua"): знімає схему, userinfo, порт і провідний "www."; повертає ""
для порожнього/невалідного входу. Раніше ця ідіома копіпастилась у ~10 місцях."""

from urllib.parse import urlsplit


def bare_host(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    netloc = urlsplit(raw if "//" in raw else "//" + raw).netloc.lower()
    netloc = netloc.split("@")[-1].split(":")[0]
    return netloc.removeprefix("www.")


# Двобуквені ccTLD, що вживаються генерично (не як країнний сигнал), тож дозволені.
_GENERIC_CCTLDS = {"co", "io", "me", "tv", "ai", "cc"}

# Однозначні коди російських міст як leading-субдомен — російський сайт на gTLD
# (spb.boombate.com). Лише безсумнівні (без коротких/двозначних, що колізять з UA).
_RU_CITY_SUBDOMAINS = frozenset({
    "spb", "msk", "mow", "ekb", "nsk", "kzn", "rostov", "sochi", "samara", "perm",
    "omsk", "ufa", "krasnodar", "volgograd", "voronezh", "tyumen", "irkutsk",
    "vladivostok", "khabarovsk", "chelyabinsk", "kaliningrad", "saratov",
    "barnaul", "tomsk", "kemerovo",
})

# IDN-ccTLD України (.укр) — punycode; єдиний дозволений xn--*. Решта IDN-ccTLD
# (xn--p1ai=.рф, xn--90ae=.бг, xn--90a3ac=.срб, ...) — іноземні.
_UA_IDN_CCTLDS = {"xn--j1amh"}

# Білоруські міста як код-сегмент (субдомен АБО сегмент шляху) — сайт агресора на
# gTLD. Куратований, без коротких/двозначних, що колізять з UA.
_BY_CITY_CODES = frozenset({
    "minsk", "gomel", "homel", "brest", "vitebsk", "vitsebsk",
    "mogilev", "mahilyow", "grodno", "hrodna", "bobruisk", "baranovichi",
})
# РФ+BY міста для гейта «весь хост геть» (Росія/Білорусь у хості АБО в шляху URL).
_RU_BY_CITY = _RU_CITY_SUBDOMAINS | _BY_CITY_CODES
_RU_BY_CCTLDS = {"ru", "by"}
_RU_BY_IDN_CCTLDS = {"xn--p1ai", "xn--90ais"}   # .рф, .бел


def is_foreign_host(value: str | None) -> bool:
    """True, якщо TLD хоста — іноземний країнний код (не Україна).

    Платформа — виключно для України. Дозволяємо .ua/*.ua і генеричні gTLD
    (com/net/org/store/shop/online/...), бо легітимні укр. бізнеси часто сидять
    не на .ua; відхиляємо іноземні ccTLD (.by/.ru/.kz/.pl/.md/...) та іноземні
    IDN-ccTLD (.рф=xn--p1ai тощо), крім українського .укр (xn--j1amh). Кілька
    ccTLD, що де-факто генеричні (co/io/me/tv/ai/cc), лишаємо дозволеними.
    Порожній/безхостовий вхід — не іноземний (нехай вирішують інші гейти)."""
    host = bare_host(value)
    if not host or "." not in host:
        return False
    if host == "ua" or host.endswith(".ua"):
        return False
    labels = host.split(".")
    if len(labels) >= 3 and labels[0] in _RU_CITY_SUBDOMAINS:
        return True                          # російський місто-субдомен на gTLD
    tld = host.rsplit(".", 1)[-1]
    if tld.startswith("xn--"):
        return tld not in _UA_IDN_CCTLDS      # foreign IDN ccTLD (allow only .укр)
    return len(tld) == 2 and tld not in _GENERIC_CCTLDS


def is_ru_by_geo(value: str | None) -> bool:
    """True, якщо URL несе сигнал Росії/Білорусі — у ccTLD (.ru/.by/.рф/.бел), у
    субдомені (spb.x.com, minsk.x.com) АБО в сегменті шляху (x.cafe/spb, x.com/minsk).

    На відміну від is_foreign_host (host-only, «іноземний ccTLD → не фетчити»), цей
    предикат читає й ШЛЯХ: місто-код у шляху видає російську/білоруську сторінку на
    інакше-дозволеному gTLD. Матч — цілий сегмент (не підрядок), тож '/spbank' не
    спрацьовує. Підтверджений UA-хост (.ua) — ніколи не РФ/BY, навіть з /spb у шляху."""
    raw = (value or "").strip()
    if not raw:
        return False
    host = bare_host(raw)
    if not host or "." not in host:
        return False
    if host == "ua" or host.endswith(".ua"):
        return False                          # confirmed-UA host wins over any path/subdomain
    tld = host.rsplit(".", 1)[-1]
    if tld in _RU_BY_CCTLDS or tld in _RU_BY_IDN_CCTLDS:
        return True
    labels = host.split(".")
    if len(labels) >= 3 and labels[0] in _RU_BY_CITY:
        return True                           # RU/BY місто-субдомен на gTLD
    path = urlsplit(raw if "//" in raw else "//" + raw).path
    return any(seg.lower() in _RU_BY_CITY for seg in path.split("/") if seg)
