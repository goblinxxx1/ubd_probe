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


def is_foreign_host(value: str | None) -> bool:
    """True, якщо TLD хоста — іноземний країнний код (не Україна).

    Платформа — виключно для України. Дозволяємо .ua/*.ua і генеричні gTLD
    (com/net/org/store/shop/online/...), бо легітимні укр. бізнеси часто сидять
    не на .ua; відхиляємо іноземні ccTLD (.by/.ru/.kz/.pl/.md/...). Кілька
    ccTLD, що де-факто генеричні (co/io/me/tv/ai/cc), лишаємо дозволеними.
    Порожній/безхостовий вхід — не іноземний (нехай вирішують інші гейти)."""
    host = bare_host(value)
    if not host or "." not in host:
        return False
    if host == "ua" or host.endswith(".ua"):
        return False
    tld = host.rsplit(".", 1)[-1]
    return len(tld) == 2 and tld not in _GENERIC_CCTLDS
