"""Реєстр хостів-каталогів (агрегаторів) + одноразова ретро-зачистка їхніх оферів.

directory_hosts — ОКРЕМА таблиця від blocked_hosts: каталог лишається fetchable
для краулера (blocked_hosts = no-fetch список), просто його офери в модерацію
не потрапляють (гейт — Task 7), а вже наявні pending-офери від краулера
зачищаються (soft-reject) одноразово при реєстрації.
"""
from app.crud.blocked_host import bare_host
from app.models.directory_host import DirectoryHost
from app.models.offer import Offer
from app.models.enums import OfferStatus, CreatedBy


def list_hosts(db) -> list[str]:
    return [r.host for r in db.query(DirectoryHost).all()]


def is_directory(db, host) -> bool:
    h = bare_host(host)
    if not h:
        return False
    return db.query(DirectoryHost).filter(DirectoryHost.host == h).first() is not None


def _sweep(db, host) -> None:
    """Ретро-відхиляє (soft-reject) наявні crawler+pending_review офери цього хоста
    (за site_url або article_url). Published та інші хости не чіпає — оборотно."""
    q = (db.query(Offer)
         .filter(Offer.created_by == CreatedBy.crawler,
                 Offer.status == OfferStatus.pending_review))
    for o in q.all():
        if bare_host(o.site_url) == host or bare_host(o.article_url) == host:
            o.status = OfferStatus.rejected
    db.commit()


def register(db, host) -> bool:
    """Реєструє хост як каталог. True — якщо щойно зареєстрований (і виконано sweep).
    Ідемпотентно: повторна реєстрація — no-op, повертає False, sweep не повторюється."""
    h = bare_host(host)
    if not h:
        return False
    if db.query(DirectoryHost).filter(DirectoryHost.host == h).first() is not None:
        return False
    db.add(DirectoryHost(host=h))
    db.commit()
    _sweep(db, h)
    return True
