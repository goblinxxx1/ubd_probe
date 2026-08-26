from crawler.discovery.rejudge import RejudgeSweep
from crawler.judge.base import Verdict
from crawler.judge.cache import VerdictCache
from crawler.judge.llama import JudgeError, JudgeUnavailable


class FakeApi:
    def __init__(self, offers):
        self._offers = offers
        self.rejected = []  # [(offer_id, reason), ...]

    def list_pending_unjudged(self, limit):
        return self._offers[:limit]

    def judge_reject_offer(self, offer_id, reason):
        self.rejected.append((offer_id, reason))


class FakeJudge:
    """Вердикт по content_hash кандидата; підтримує виняток на конкретному hash."""

    def __init__(self, verdicts=None, raise_on=None):
        self._verdicts = verdicts or {}
        self._raise_on = raise_on or {}
        self.calls = []

    def verdict(self, cand):
        h = cand.content_hash if hasattr(cand, "content_hash") else None
        # cand — SimpleNamespace без content_hash (за контрактом), тому матчимо по title
        self.calls.append(cand.title)
        if cand.title in self._raise_on:
            raise self._raise_on[cand.title]
        return self._verdicts[cand.title]


def _offer(id, title, ch, description="text", discount_type="percent", discount_value=10,
           article_url="https://example.com/x"):
    return {"id": id, "title": title, "description": description,
            "discount_type": discount_type, "discount_value": discount_value,
            "article_url": article_url, "content_hash": ch}


def test_junk_rejected_genuine_kept_already_cached_skipped(tmp_path):
    cache = VerdictCache(str(tmp_path / "c.json"))
    cache.put("cached-hash", Verdict(True, True, "already judged"))

    offers = [
        _offer(1, "junk offer", "junk-hash"),
        _offer(2, "genuine offer", "genuine-hash"),
        _offer(3, "old offer", "cached-hash"),
    ]
    judge = FakeJudge(verdicts={
        "junk offer": Verdict(False, True, "не для цієї аудиторії"),
        "genuine offer": Verdict(True, True, "реальна знижка"),
    })
    api = FakeApi(offers)

    sweep = RejudgeSweep(api, judge, cache, budget=30)
    counts = sweep.run()

    assert judge.calls == ["junk offer", "genuine offer"]  # cached offer НЕ судили
    assert api.rejected == [(1, "суддя: не для цієї аудиторії")]
    assert cache.get("junk-hash") is not None
    assert cache.get("genuine-hash").genuine is True
    assert counts == {"scanned": 2, "kept": 1, "rejected": 1, "skipped": 1}


def test_judge_unavailable_stops_sweep_without_rejecting_rest(tmp_path):
    cache = VerdictCache(str(tmp_path / "c.json"))
    offers = [
        _offer(1, "junk offer", "junk-hash"),
        _offer(2, "unreachable offer", "unreachable-hash"),
        _offer(3, "would-be-junk offer", "would-be-junk-hash"),
    ]
    judge = FakeJudge(
        verdicts={"junk offer": Verdict(False, True, "junk")},
        raise_on={"unreachable offer": JudgeUnavailable("connection refused")},
    )
    api = FakeApi(offers)

    sweep = RejudgeSweep(api, judge, cache, budget=30)
    counts = sweep.run()

    # перший офер устиг обробитись і бути відхиленим до того, як суддя став недосяжний
    assert api.rejected == [(1, "суддя: junk")]
    # третій офер НІКОЛИ не діставався судді -> нічого хибно не відхилено після зупинки
    assert judge.calls == ["junk offer", "unreachable offer"]
    assert cache.get("would-be-junk-hash") is None
    assert counts["scanned"] == 2
    assert counts["rejected"] == 1


def test_judge_error_skips_candidate_and_continues(tmp_path):
    cache = VerdictCache(str(tmp_path / "c.json"))
    offers = [
        _offer(1, "bad-body offer", "bad-body-hash"),
        _offer(2, "genuine offer", "genuine-hash-2"),
    ]
    judge = FakeJudge(
        verdicts={"genuine offer": Verdict(True, True, "ok")},
        raise_on={"bad-body offer": JudgeError("400 bad request")},
    )
    api = FakeApi(offers)

    sweep = RejudgeSweep(api, judge, cache, budget=30)
    counts = sweep.run()

    assert api.rejected == []                       # проблемний кандидат НЕ відхилено
    assert cache.get("bad-body-hash") is None        # лишається на наступний прохід
    assert cache.get("genuine-hash-2").genuine is True
    assert counts == {"scanned": 2, "kept": 1, "rejected": 0, "skipped": 1}
