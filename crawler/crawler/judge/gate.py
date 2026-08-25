"""RelevanceGate: суддя + кеш + circuit-breaker + деградація.

keep(candidate) = genuine AND page_scoped. Недоступний суддя (виняток) або
enabled=False -> keep=True (поведінка як сьогодні). Після падіння виклику —
breaker глушить подальші виклики до reset_breaker() (початок кожного проходу)."""

import logging

from crawler.judge.llama import JudgeError, JudgeUnavailable

log = logging.getLogger(__name__)


class RelevanceGate:
    def __init__(self, judge, cache, enabled: bool = True):
        self._judge = judge
        self._cache = cache
        self._enabled = bool(enabled)
        self._broken = False

    def reset_breaker(self) -> None:
        self._broken = False

    def keep(self, candidate) -> bool:
        if not self._enabled or self._broken:
            return True
        content_hash = getattr(candidate, "content_hash", None)
        if content_hash and self._cache is not None:
            cached = self._cache.get(content_hash)
            if cached is not None:
                return cached.genuine and cached.page_scoped
        try:
            v = self._judge.verdict(candidate)
        except JudgeUnavailable as exc:
            self._broken = True
            log.warning("relevance judge unavailable, degrading to keep-all this pass: %s", exc)
            return True
        except JudgeError as exc:  # per-candidate: скіп лише цього, breaker незмінний
            log.warning("relevance judge skipped this candidate (fail-open): %s", exc)
            return True
        if content_hash and self._cache is not None:
            try:
                self._cache.put(content_hash, v)
            except Exception as exc:  # noqa: BLE001 — запис кешу best-effort, не блокує офер
                log.warning("verdict cache write failed: %s", exc)
        return v.genuine and v.page_scoped
