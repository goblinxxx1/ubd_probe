"""Семантичний relevance-суддя: контракт і no-op реалізація.

Суддя — strictly-additive шар над евристикою. `NullJudge` (дефолт/деградація)
завжди пропускає → поведінка як сьогодні, нуль регресії."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Verdict:
    genuine: bool          # реальна знижка/вигода САМЕ цій аудиторії (не випадковий збіг слів)
    page_scoped: bool      # промо саме цієї сторінки (не сайт-широкий банер на чужій сторінці)
    reason: str


class Judge(Protocol):
    def verdict(self, candidate) -> Verdict:
        ...


class NullJudge:
    """Деградація/вимкнено: усе genuine+page_scoped → keep завжди True."""

    def verdict(self, candidate) -> Verdict:
        return Verdict(genuine=True, page_scoped=True, reason="judge disabled")
