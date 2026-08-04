import json
import types

from crawler.learn.run_query_miner import run_query_miner


def _cfg(tmp_path, **over):
    corpus = tmp_path / "corpus.jsonl"
    # two approved (pass) offers mentioning a service noun on distinct hosts; one fail
    rows = [
        {"text": "стоматологія знижка", "label": "pass", "host": "a.com", "snowball": True},
        {"text": "стоматологія акція", "label": "pass", "host": "b.com", "snowball": True},
        {"text": "стоматологія клініка", "label": "pass", "host": "c.com", "snowball": True},
        {"text": "новини політика", "label": "fail", "host": "n.com"},
    ]
    corpus.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    d = dict(corpus_path=str(corpus),
             query_candidates_path=str(tmp_path / "q_cand.json"),
             query_stoplist_path=str(tmp_path / "q_stop.json"),
             query_lexicon_learned_path=str(tmp_path / "q_learned.json"),
             query_miner_min_domain_support=2, query_miner_min_logodds=0.1,
             query_miner_max_candidates_per_run=50, query_lexicon_resurface_factor=2.0)
    d.update(over)
    return types.SimpleNamespace(**d)


def test_run_query_miner_writes_service_candidates(tmp_path):
    cfg = _cfg(tmp_path)
    n = run_query_miner(cfg)
    cand = json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())
    terms = [c["term"] for c in cand]
    assert "стоматологія" in terms
    assert "політика" not in terms          # noun but from FAIL side -> low/neg z
    assert n == len(cand)


def test_run_query_miner_respects_soft_stoplist(tmp_path):
    cfg = _cfg(tmp_path)
    # pre-block "стоматологія" with a high z so factor keeps it suppressed
    open(cfg.query_stoplist_path, "w", encoding="utf-8").write(
        json.dumps([{"term": "стоматологія", "z": 100.0}]))
    run_query_miner(cfg)
    cand = json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())
    assert "стоматологія" not in [c["term"] for c in cand]
