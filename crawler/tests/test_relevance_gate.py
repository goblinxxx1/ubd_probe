from crawler.judge.base import Verdict, NullJudge
from crawler.judge.cache import VerdictCache
from crawler.judge.llama import JudgeError
from crawler.judge.gate import RelevanceGate


class _Cand:
    def __init__(self, h): self.content_hash = h


class FakeJudge:
    def __init__(self, verdict=None, exc=None):
        self._v = verdict
        self._exc = exc
        self.calls = 0
    def verdict(self, cand):
        self.calls += 1
        if self._exc:
            raise self._exc
        return self._v


def _gate(tmp_path, judge, enabled=True):
    return RelevanceGate(judge, VerdictCache(str(tmp_path / "c.json")), enabled=enabled)


def test_disabled_gate_always_keeps(tmp_path):
    j = FakeJudge(Verdict(False, False, "junk"))
    g = _gate(tmp_path, j, enabled=False)
    assert g.keep(_Cand("h")) is True
    assert j.calls == 0                       # disabled -> judge never called


def test_junk_dropped_genuine_kept(tmp_path):
    assert _gate(tmp_path, FakeJudge(Verdict(False, True, "song"))).keep(_Cand("h1")) is False
    assert _gate(tmp_path, FakeJudge(Verdict(True, False, "banner"))).keep(_Cand("h2")) is False
    assert _gate(tmp_path, FakeJudge(Verdict(True, True, "real"))).keep(_Cand("h3")) is True


def test_cache_hit_skips_judge(tmp_path):
    j = FakeJudge(Verdict(False, True, "song"))
    g = _gate(tmp_path, j)
    assert g.keep(_Cand("dup")) is False
    assert g.keep(_Cand("dup")) is False
    assert j.calls == 1                       # second call served from cache


def test_judge_error_degrades_and_trips_breaker(tmp_path):
    j = FakeJudge(exc=JudgeError("down"))
    g = _gate(tmp_path, j)
    assert g.keep(_Cand("a")) is True         # degrade: keep as today
    assert g.keep(_Cand("b")) is True         # breaker tripped -> no further calls
    assert j.calls == 1
    g.reset_breaker()
    assert g.keep(_Cand("c")) is True
    assert j.calls == 2                        # breaker reset -> judge called again
