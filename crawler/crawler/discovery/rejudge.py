"""RejudgeSweep: доганяльний прохід судді по вже опублікованих у чергу
pending-офферах, які проскочили без вердикту (суддя був недосяжний /
вимкнений / доданий пізніше). Не блокує основний краулінг — окремий,
рідший прохід (wiring — Task 5).

Правила ідентичні RelevanceGate (крок за кроком):
- офер із вердиктом уже в кеші (по content_hash) -> пропускаємо, суддю не кличемо;
- JudgeUnavailable (суддя недосяжний) -> ЗУПИНЯЄМО весь прохід негайно, нічого
  далі не відхиляємо (fail-safe: ніколи не ріжемо наосліп, коли суддя мовчить);
- JudgeError (проблема з ЦИМ кандидатом) -> скіпаємо його, прохід триває
  (лишаємо на наступний sweep, не відхиляємо про всяк випадок);
- genuine AND page_scoped -> кешуємо вердикт, лишаємо як є (kept);
- інакше -> м'яко відхиляємо через API + кешуємо вердикт (щоб повторний
  список pending-unjudged більше на нього не натрапляв)."""

import logging
import types

from crawler.judge.llama import JudgeError, JudgeUnavailable

log = logging.getLogger(__name__)


class RejudgeSweep:
    def __init__(self, api, judge, cache, *, budget: int = 30):
        self._api = api
        self._judge = judge
        self._cache = cache
        self._budget = budget

    def run(self) -> dict:
        counts = {"scanned": 0, "kept": 0, "rejected": 0, "skipped": 0}
        offers = self._api.list_pending_unjudged(self._budget)
        for offer in offers:
            content_hash = offer.get("content_hash")
            if content_hash and self._cache.get(content_hash) is not None:
                # уже суджений раніше (кеш） -> нема сенсу питати суддю вдруге
                counts["skipped"] += 1
                continue

            counts["scanned"] += 1
            cand = types.SimpleNamespace(
                title=offer["title"],
                body=offer.get("description") or "",
                discount_type=offer.get("discount_type"),
                discount_value=offer.get("discount_value"),
                article_url=offer.get("article_url"),
            )
            try:
                verdict = self._judge.verdict(cand)
            except JudgeUnavailable as exc:
                log.warning("суддя недосяжний, зупиняємо re-judge sweep: %s", exc)
                break
            except JudgeError as exc:
                log.warning("суддя пропустив кандидата %s (fail-open, наступний sweep): %s",
                            offer.get("id"), exc)
                counts["skipped"] += 1
                continue

            if verdict.genuine and verdict.page_scoped:
                if content_hash:
                    self._cache.put(content_hash, verdict)
                counts["kept"] += 1
            else:
                try:
                    self._api.judge_reject_offer(offer["id"], reason=f"суддя: {verdict.reason}")
                except Exception as exc:  # noqa: BLE001 — один невдалий reject (напр. HTTP 5xx)
                    # не має топити весь sweep (Task-4 review). НЕ кешуємо вердикт і НЕ
                    # рахуємо як rejected — офер лишається pending-unjudged, наступний
                    # sweep спробує відхилити знову.
                    log.warning("re-judge: reject офера %s не вдався, лишаємо на наступний sweep: %s",
                                offer.get("id"), exc)
                    counts["skipped"] += 1
                    continue
                if content_hash:
                    self._cache.put(content_hash, verdict)
                counts["rejected"] += 1
        return counts
