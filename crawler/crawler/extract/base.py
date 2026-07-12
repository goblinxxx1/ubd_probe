from dataclasses import dataclass, field
from typing import Protocol

from crawler.models import OfferCandidate, RawItem


@dataclass
class CategoryIndex:
    target: list[dict] = field(default_factory=list)
    offer: list[dict] = field(default_factory=list)


class Extractor(Protocol):
    def extract(self, item: RawItem, provider: str,
                categories: CategoryIndex) -> OfferCandidate | None:
        ...


def get_extractor(name: str) -> Extractor:
    if name == "heuristic":
        from crawler.extract.heuristic import HeuristicExtractor
        return HeuristicExtractor()
    if name == "local_llm":
        raise NotImplementedError("local_llm extractor is a hook only; not implemented")
    raise ValueError(f"Unknown extractor: {name}")
