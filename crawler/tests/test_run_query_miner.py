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
             query_miner_min_pass_docs=1,
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


def test_run_query_miner_known_stems_are_case_insensitive(tmp_path):
    cfg = _cfg(tmp_path)
    open(cfg.query_lexicon_learned_path, "w", encoding="utf-8").write(
        json.dumps([{"term": "Стоматологія", "source": "category"}]))
    n = run_query_miner(cfg)
    cand = json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())
    terms = [c["term"] for c in cand]
    assert "стоматологія" not in terms
    assert n == len(cand)


def test_run_query_miner_respects_soft_stoplist(tmp_path):
    cfg = _cfg(tmp_path)
    # pre-block "стоматологія" with a high z so factor keeps it suppressed
    open(cfg.query_stoplist_path, "w", encoding="utf-8").write(
        json.dumps([{"term": "стоматологія", "z": 100.0}]))
    run_query_miner(cfg)
    cand = json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())
    assert "стоматологія" not in [c["term"] for c in cand]


def test_run_query_miner_vetoes_audience_and_intent(tmp_path):
    import json as _json
    corpus = tmp_path / "corpus.jsonl"
    rows = [
        {"text": "стоматологія знижка ветеран", "label": "pass", "host": "a.com", "snowball": True},
        {"text": "стоматологія акція ветеран", "label": "pass", "host": "b.com", "snowball": True},
        {"text": "стоматологія клініка ветеран", "label": "pass", "host": "c.com", "snowball": True},
        {"text": "новини політика", "label": "fail", "host": "n.com"},
    ]
    corpus.write_text("\n".join(_json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    cfg = _cfg(tmp_path, corpus_path=str(corpus))
    run_query_miner(cfg)
    terms = [c["term"] for c in _json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())]
    assert "стоматологія" in terms       # real service survives
    assert "ветеран" not in terms        # audience axis vetoed
    assert "знижка" not in terms         # intent axis vetoed


def _corpus(tmp_path, rows):
    # distinct filename: _cfg() also writes tmp_path/corpus.jsonl and would clobber this
    p = tmp_path / "corpus_custom.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return str(p)


def test_ranks_by_cross_host_support(tmp_path):
    # "стоматологія" on 3 hosts, "перукарня" on 1 host — support orders them.
    rows = [
        {"text": "стоматологія клініка", "label": "pass", "host": "a.com", "snowball": True},
        {"text": "стоматологія акція", "label": "pass", "host": "b.com", "snowball": True},
        {"text": "стоматологія знижка", "label": "pass", "host": "c.com", "snowball": True},
        {"text": "перукарня послуга", "label": "pass", "host": "a.com", "snowball": True},
        {"text": "перукарня стрижка", "label": "pass", "host": "a.com", "snowball": True},
    ]
    cfg = _cfg(tmp_path, corpus_path=_corpus(tmp_path, rows), query_miner_min_domain_support=1)
    run_query_miner(cfg)
    terms = [c["term"] for c in json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())]
    assert terms.index("стоматологія") < terms.index("перукарня")   # higher support first


def test_surfaces_single_host_service(tmp_path):
    # floor=1: a service on ONE host still surfaces (recall NOW, not after a 2nd business).
    rows = [
        {"text": "відбілювання зубів", "label": "pass", "host": "a.com", "snowball": True},
        {"text": "відбілювання акція", "label": "pass", "host": "a.com", "snowball": True},
    ]
    cfg = _cfg(tmp_path, corpus_path=_corpus(tmp_path, rows), query_miner_min_domain_support=1)
    run_query_miner(cfg)
    terms = [c["term"] for c in json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())]
    assert "відбілювання" in terms


def test_hapax_guard_drops_single_doc_term(tmp_path):
    # "фотозйомка" appears in exactly ONE pass doc -> anti-typo hapax guard drops it;
    # "манікюр" appears in two -> survives.
    rows = [
        {"text": "манікюр послуга", "label": "pass", "host": "a.com", "snowball": True},
        {"text": "манікюр знижка", "label": "pass", "host": "a.com", "snowball": True},
        {"text": "фотозйомка", "label": "pass", "host": "a.com", "snowball": True},
    ]
    cfg = _cfg(tmp_path, corpus_path=_corpus(tmp_path, rows),
               query_miner_min_domain_support=1, query_miner_min_pass_docs=2)
    run_query_miner(cfg)
    terms = [c["term"] for c in json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())]
    assert "манікюр" in terms
    assert "фотозйомка" not in terms


def test_excludes_moderator_rejected_terms(tmp_path):
    cfg = _cfg(tmp_path, query_miner_min_domain_support=1)
    run_query_miner(cfg, rejected_terms=["Стоматологія"])   # case-insensitive
    terms = [c["term"] for c in json.loads(open(cfg.query_candidates_path, encoding="utf-8").read())]
    assert "стоматологія" not in terms
