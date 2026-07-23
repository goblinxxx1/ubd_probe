"""Детермінований labeler: мітка PASS/FAIL з гейта екстракції + якорі
(negative = blocklist-host, positive = schema.org Offer)."""

from dataclasses import dataclass

from crawler.discovery.blocklist import is_blocked_host
from crawler.util.hosts import bare_host


@dataclass
class LabelRecord:
    label: str          # "pass" | "fail"
    host: str
    neg_anchor: bool
    pos_anchor: bool
    is_article: bool = False


def _host(url: str | None) -> str:
    return bare_host(url)


def label_item(item, extracted_is_offer: bool) -> LabelRecord:
    host = _host(getattr(item, "url", None))
    return LabelRecord(
        label="pass" if extracted_is_offer else "fail",
        host=host,
        neg_anchor=is_blocked_host(host),
        pos_anchor=bool(getattr(item, "has_offer_schema", False)),
        is_article=bool(getattr(item, "is_article", False)),
    )
