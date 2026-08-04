"""Offline QUERY miner: corpus → service-noun log-odds → soft-stoplist filter →
candidate queue for human audit. Mirror of run_miner, for the query lexicon."""

from crawler.discovery import query_lexicon as ql
from crawler.learn.audit import write_candidates
from crawler.learn.corpus import read_corpus
from crawler.learn.miner import mine
from crawler.learn.tokenize import service_terms
from crawler.learn.query_stoplist import load_blocked, is_suppressed
from crawler.learn.vetoes import survivors


def run_query_miner(config) -> int:
    ql.reload_learned(getattr(config, "query_lexicon_learned_path", None))
    rows = read_corpus(config.corpus_path)
    known = tuple(s.casefold() for s in ql.learned_services())
    scores = mine(rows, known_stems=known, stoplist=(), tokenizer=service_terms)
    blocked = load_blocked(config.query_stoplist_path)
    factor = config.query_lexicon_resurface_factor
    scores = [s for s in scores if not is_suppressed(s.term, s.z, blocked, factor)]
    keep = survivors(scores, min_domains=config.query_miner_min_domain_support,
                     min_z=config.query_miner_min_logodds,
                     max_candidates=config.query_miner_max_candidates_per_run)
    write_candidates(config.query_candidates_path, keep)
    return len(keep)


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    import logging

    from crawler.config import load_config

    logging.basicConfig(level=logging.INFO)
    n = run_query_miner(load_config())
    print(f"query candidates written: {n}")
