from typing import Protocol

from crawler.models import RawItem


class Fetcher(Protocol):
    platform: str

    def fetch(self, source: dict,
              last_seen_key: str | None) -> tuple[list[RawItem], str | None]:
        ...
