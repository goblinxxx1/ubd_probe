from crawler.discovery.providers import SearxngProvider


class _Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t


class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


class _Client:
    def __init__(self, payload=None, boom=False, seen=None):
        self._payload = payload or {"results": []}
        self._boom = boom
        self._seen = seen
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get(self, url, params=None):
        if self._seen is not None:
            self._seen.append(params)
        if self._boom:
            raise RuntimeError("connection refused")
        return _Resp(self._payload)


def test_parses_results_into_candidates():
    payload = {"results": [{"title": "Крамниця", "url": "https://shop.ua/x"}]}
    p = SearxngProvider("http://searxng:8080", client_factory=lambda: _Client(payload),
                        sleep=lambda _s: None)
    cands = p("знижки військовим")
    assert cands[0].type == "website"
    assert cands[0].url_or_handle == "https://shop.ua/x"
    assert cands[0].discovery_note == "searxng: знижки військовим"
    assert p.succeeded() is True
    assert p.available() is True


def test_pageno_forwarded_only_when_gt1():
    seen = []
    p = SearxngProvider("http://searxng:8080",
                        client_factory=lambda: _Client({"results": []}, seen=seen),
                        sleep=lambda _s: None)
    p("kw")                       # page 1 → no pageno (byte-eq)
    assert "pageno" not in seen[-1]
    p("kw", page=2)               # page 2 → pageno=2
    assert seen[-1]["pageno"] == 2


def test_last_served_true_on_http_success_even_empty():
    p = SearxngProvider("http://searxng:8080",
                        client_factory=lambda: _Client({"results": []}), sleep=lambda _s: None)
    assert p("kw") == []
    assert p.last_served is True             # HTTP 200 with an (empty) result set = served


def test_last_served_false_on_failure():
    p = SearxngProvider("http://searxng:8080", client_factory=lambda: _Client(boom=True),
                        sleep=lambda _s: None)
    assert p("kw") == []
    assert p.last_served is False            # HTTP/transport failure = censored


def test_last_served_false_when_cooled():
    clock = _Clock()
    p = SearxngProvider("http://searxng:8080", client_factory=lambda: _Client(boom=True),
                        sleep=lambda _s: None, clock=clock, fail_threshold=1, cooldown_base=100.0)
    p("kw")                                   # fails → trips its own cooldown
    assert p.available() is False
    p("kw")                                   # skipped while cooled
    assert p.last_served is False


def test_failure_cools_after_threshold():
    clock = _Clock()
    p = SearxngProvider("http://searxng:8080", client_factory=lambda: _Client(boom=True),
                        sleep=lambda _s: None, clock=clock, fail_threshold=3,
                        cooldown_base=100.0, cooldown_cap=1000.0)
    for _ in range(3):
        assert p("kw") == []
    assert p.available() is False           # 3rd failure trips its own cooldown
    clock.t += 1000                          # cooldown elapsed
    assert p.available() is True
