from crawler.learn.run_host_miner import run_host_miner


class _Cfg:
    corpus_path = None
    host_miner_min_support = 3
    host_miner_media_min = 0.5
    host_miner_aggregator_min = 0.5
    aggregator_min_outbound = 3
    host_miner_max_candidates = 50


class _Api:
    def __init__(self): self.sent = []
    def submit_host_candidate(self, payload): self.sent.append(payload); return {}


def test_run_host_miner_submits_survivors(tmp_path, monkeypatch):
    import crawler.learn.run_host_miner as m
    rows = [{"host": "blog.ua", "label": "pass", "is_article": True,
             "outbound_hosts": 0, "pos_anchor": False, "text": "https://blog.ua/a"}
            for _ in range(4)]
    monkeypatch.setattr(m, "read_corpus", lambda p: rows)
    api = _Api()
    n = run_host_miner(_Cfg(), api, protected_hosts=set())
    assert n == 1
    assert api.sent[0]["host"] == "blog.ua" and api.sent[0]["support"] == 4


def test_run_host_miner_respects_protected(tmp_path, monkeypatch):
    import crawler.learn.run_host_miner as m
    rows = [{"host": "blog.ua", "label": "pass", "is_article": True,
             "outbound_hosts": 0, "pos_anchor": False, "text": "u"} for _ in range(4)]
    monkeypatch.setattr(m, "read_corpus", lambda p: rows)
    api = _Api()
    assert run_host_miner(_Cfg(), api, protected_hosts={"blog.ua"}) == 0


def test_run_host_miner_respects_protected_full_url(tmp_path, monkeypatch):
    # CLI passes url_or_handle for website sources, which is a full URL
    # (e.g. "https://blog.ua"), not a bare host — must still veto.
    import crawler.learn.run_host_miner as m
    rows = [{"host": "blog.ua", "label": "pass", "is_article": True,
             "outbound_hosts": 0, "pos_anchor": False, "text": "u"} for _ in range(4)]
    monkeypatch.setattr(m, "read_corpus", lambda p: rows)
    api = _Api()
    assert run_host_miner(_Cfg(), api, protected_hosts={"https://blog.ua"}) == 0
