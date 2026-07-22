"""§2: bootstrapped корпус → майнер → вето → approve → живий гейт ловить новий терм.

Наскрізний тест: жодна стадія не застабльована — реальні run_miner, audit.approve,
promo_lexicon, HeuristicExtractor. Єдина фікстура — сирий JSONL-корпус.
"""
import json

from crawler.discovery import promo_lexicon as pl
from crawler.extract.base import CategoryIndex, get_extractor
from crawler.learn.audit import approve
from crawler.learn.run_miner import run_miner
from crawler.models import RawItem


class _Cfg:
    miner_min_domain_support = 3
    miner_min_logodds = 1.5
    miner_max_candidates_per_run = 50


def _cats():
    return CategoryIndex(target=[{"id": 10, "name": "Ветеран", "slug": "veteran"}], offer=[])


def test_end_to_end_autofill(tmp_path):
    # 1) корпус: "рібейт" (не в SEED_OFFER_TRIGGERS) у PASS на 4 різних доменах,
    # плюс нейтральний новинний шум у FAIL — жодного спільного терму з PASS.
    assert "рібейт" not in pl.SEED_OFFER_TRIGGERS
    rows = ([{"text": "рібейт для ветеранів", "label": "pass", "host": f"d{i}.ua",
              "neg_anchor": False, "snowball": False} for i in range(4)]
            + [{"text": "новина міста сьогодні", "label": "fail", "host": f"n{i}.ua",
               "neg_anchor": False, "snowball": False} for i in range(4)])
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows),
                      encoding="utf-8")

    cfg = _Cfg()
    cfg.corpus_path = str(corpus)
    cfg.promo_lexicon_learned_path = str(tmp_path / "learned.json")
    cfg.candidates_path = str(tmp_path / "candidates.json")
    cfg.stoplist_path = str(tmp_path / "stop.json")

    try:
        # 2) майнер + вето → черга кандидатів
        n = run_miner(cfg)
        assert n >= 1
        cand_terms = [c["term"] for c in json.load(open(cfg.candidates_path, encoding="utf-8"))]
        assert "рібейт" in cand_terms

        # 3) approve → LEARNED
        approve("рібейт", cfg.candidates_path, cfg.promo_lexicon_learned_path)
        learned = json.load(open(cfg.promo_lexicon_learned_path, encoding="utf-8"))
        assert any(e.get("term") == "рібейт" for e in learned)

        # 4) reload + живий гейт тепер ловить новий терм (не ловив би без approve)
        pl.reload_learned(cfg.promo_lexicon_learned_path)
        assert "рібейт" in pl.offer_triggers()

        ex = get_extractor("heuristic")
        item = RawItem(source_id=1, platform="website", key="k",
                       text="Рібейт для ветеранів у нашому магазині")
        result = ex.extract(item, "Shop", _cats())
        assert result is not None
        assert result.target_category_ids == [10]
    finally:
        pl.reload_learned(None)  # reset global state for other tests
