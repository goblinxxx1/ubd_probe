"""Офлайн-оркестратор: корпус → майнер → вето → черга кандидатів."""

from crawler.discovery import promo_lexicon as pl
from crawler.learn.audit import load_stoplist, write_candidates
from crawler.learn.corpus import read_corpus
from crawler.learn.miner import mine
from crawler.learn.vetoes import survivors


def run_miner(config) -> int:
    pl.reload_learned(getattr(config, "promo_lexicon_learned_path", None))
    rows = read_corpus(config.corpus_path)
    known = pl.offer_triggers()
    stop = load_stoplist(getattr(config, "stoplist_path", None))
    scores = mine(rows, known_stems=known, stoplist=stop)
    keep = survivors(scores, min_domains=config.miner_min_domain_support,
                     min_z=config.miner_min_logodds,
                     max_candidates=config.miner_max_candidates_per_run)
    write_candidates(config.candidates_path, keep)
    return len(keep)
