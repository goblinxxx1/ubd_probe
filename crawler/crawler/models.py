from dataclasses import dataclass, field
from datetime import date


@dataclass
class BotCredential:
    platform: str
    username: str
    password: str


@dataclass
class RawItem:
    source_id: int
    platform: str
    key: str                 # stable per-item cursor key (e.g. post id / hash)
    text: str
    url: str | None = None
    links: list[str] = field(default_factory=list)
    logo_url: str | None = None


@dataclass
class OfferCandidate:
    source_id: int
    title: str
    provider: str
    body: str
    offer_type: str = "discount"          # "discount" | "event"
    discount_type: str | None = None      # "percent" | "fixed" | "free"
    discount_value: str | None = None     # decimal as string, or None
    valid_from: date | None = None
    valid_until: date | None = None
    content_hash: str = ""
    site_url: str | None = None
    article_url: str | None = None
    image_url: str | None = None
    target_category_ids: list[int] = field(default_factory=list)
    offer_category_ids: list[int] = field(default_factory=list)


@dataclass
class SourceCandidate:
    name: str
    type: str
    url_or_handle: str
    discovered_from_source_id: int | None = None
    discovery_note: str | None = None
