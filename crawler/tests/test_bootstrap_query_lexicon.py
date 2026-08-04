import json
import types

from crawler.learn.bootstrap_query_lexicon import bootstrap


class _Api:
    def __init__(self, rows): self._rows = rows
    def list_approved_offers(self, since=None):
        assert since is None            # full backfill
        return self._rows


class _Rec:
    def __init__(self): self.texts = []
    def record(self, item, is_offer, *, snowball=False):
        self.texts.append(item.text)


def _cfg(tmp_path):
    return types.SimpleNamespace(
        corpus_path=str(tmp_path / "corpus.jsonl"),
        query_candidates_path=str(tmp_path / "q_cand.json"),
        query_stoplist_path=str(tmp_path / "q_stop.json"),
        query_lexicon_learned_path=str(tmp_path / "q_learned.json"),
        query_miner_min_domain_support=1, query_miner_min_logodds=0.1,
        query_miner_max_candidates_per_run=50, query_lexicon_resurface_factor=2.0)


def test_bootstrap_seeds_categories_and_feeds_corpus(tmp_path):
    cfg = _cfg(tmp_path)
    api = _Api([
        {"text": "Стоматологія Люкс\nзнижка", "host": "a.com", "categories": ["Медицина"]},
        {"text": "Автосервіс\nакція", "host": "b.com", "categories": ["Авто", "Медицина"]},
    ])
    rec = _Rec()
    n_cat, n_cand = bootstrap(cfg, api, rec)
    learned = json.loads(open(cfg.query_lexicon_learned_path, encoding="utf-8").read())
    cats = [e["term"] for e in learned if e.get("source") == "category"]
    assert set(cats) == {"Медицина", "Авто"} and n_cat == 2      # deduped
    assert len(rec.texts) == 2                                    # both offer texts fed
    assert isinstance(n_cand, int)


def test_bootstrap_unstops_a_category(tmp_path):
    cfg = _cfg(tmp_path)
    open(cfg.query_stoplist_path, "w", encoding="utf-8").write(
        json.dumps([{"term": "Медицина", "z": 9.0}]))
    api = _Api([{"text": "x\ny", "host": "a.com", "categories": ["Медицина"]}])
    bootstrap(cfg, api, _Rec())
    stop = json.loads(open(cfg.query_stoplist_path, encoding="utf-8").read())
    assert all(e["term"] != "Медицина" for e in stop)             # auto-unstopped
