import json
from crawler.learn.run_miner import run_miner


class _Cfg:
    corpus_path = None
    promo_lexicon_learned_path = None
    miner_min_domain_support = 3
    miner_min_logodds = 1.5
    miner_max_candidates_per_run = 50


def test_run_miner_writes_candidates(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    # "суперхіт" (не "уцінка"): "уцінк" вже в SEED_OFFER_TRIGGERS
    # (promo_lexicon), тож known_stems виключив би його з mine() ще до
    # запису кандидатів — тест мусить брати термін, якого ще НЕМА в
    # відомому лексиконі, інакше він ніколи не потрапить у candidates.
    lines = ([{"text": "суперхіт на все", "label": "pass", "host": f"d{i}.ua",
               "neg_anchor": False, "snowball": False} for i in range(4)]
             + [{"text": "звичайна новина", "label": "fail", "host": f"n{i}.ua",
                 "neg_anchor": False, "snowball": False} for i in range(4)])
    corpus.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines),
                      encoding="utf-8")
    cfg = _Cfg()
    cfg.corpus_path = str(corpus)
    cfg.promo_lexicon_learned_path = str(tmp_path / "learned.json")
    cfg.candidates_path = str(tmp_path / "candidates.json")
    cfg.stoplist_path = str(tmp_path / "stop.json")
    n = run_miner(cfg)
    assert n >= 1
    terms = [c["term"] for c in json.load(open(cfg.candidates_path, encoding="utf-8"))]
    assert "суперхіт" in terms
