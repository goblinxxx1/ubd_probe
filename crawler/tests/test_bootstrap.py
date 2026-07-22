from crawler.learn.bootstrap import bootstrap


class _Cfg:
    corpus_path = None
    corpus_max_mb = 10.0
    extractor = "heuristic"
    request_timeout = 5.0
    # brand-feed вимкнено у тесті → bootstrap має коректно повернути 0
    brand_feed_enabled = False


def test_bootstrap_no_brandfeed_returns_zero(tmp_path):
    cfg = _Cfg()
    cfg.corpus_path = str(tmp_path / "corpus.jsonl")
    assert bootstrap(cfg) == 0
