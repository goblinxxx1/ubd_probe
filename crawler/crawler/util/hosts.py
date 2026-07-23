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
