"""Offline QUERY miner: corpus → service-noun log-odds → soft-stoplist filter →
candidate queue for human audit. Mirror of run_miner, for the query lexicon."""

from crawler.discovery import query_lexicon as ql
from crawler.learn.audit import write_candidates
from crawler.learn.axis_veto import axis_veto_terms, is_axis_or_noise
from crawler.learn.corpus import read_corpus
from crawler.learn.miner import mine
from crawler.learn.tokenize import service_terms
from crawler.learn.query_stoplist import load_blocked, is_suppressed
from crawler.learn.vetoes import survivors


def _support(s) -> int:
    return len({d for d in s.domains if d})


def run_query_miner(config, rejected_terms=()) -> int:
    ql.reload_learned(getattr(config, "query_lexicon_learned_path", None))
    rows = read_corpus(config.corpus_path)
    known = tuple(s.casefold() for s in ql.learned_services())
    scores = mine(rows, known_stems=known, stoplist=(), tokenizer=service_terms)
    # Axis-veto: drop grid-axis (audience/intent/city) and generic/geo words — they are
    # distinctive to our offers so log-odds ranks them high, but they are NOT services.
    veto = axis_veto_terms()
    scores = [s for s in scores if not is_axis_or_noise(s.term, veto)]
    blocked = load_blocked(config.query_stoplist_path)
    factor = config.query_lexicon_resurface_factor
    scores = [s for s in scores if not is_suppressed(s.term, s.z, blocked, factor)]
    # Hard-exclude moderator-rejected terms (backend audit memory): while a term is
    # rejected it must never re-enter the queue — no soft resurface. (v2)
    rej = {t.strip().casefold() for t in (rejected_terms or ()) if t}
    if rej:
        scores = [s for s in scores if s.term.casefold() not in rej]
    # Rank by cross-host SUPPORT (the degenerate all-pass log-odds z must neither rank nor
    # gate); tiebreak by weighted pass_count, then term for stability. (v2)
    scores.sort(key=lambda s: (-_support(s), -s.pass_count, s.term))
    # cap<=0 means "все зразу" — clamp to a generous safety ceiling to avoid a
    # pathological unbounded submit.
    cap = config.query_miner_max_candidates_per_run
    cap = cap if cap and cap > 0 else 1000
    keep = survivors(scores, min_domains=config.query_miner_min_domain_support,
                     min_z=None, max_candidates=cap,
                     min_pass_docs=config.query_miner_min_pass_docs)
    write_candidates(config.query_candidates_path, keep)
    return len(keep)


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    import logging

    from crawler.config import load_config

    logging.basicConfig(level=logging.INFO)
    n = run_query_miner(load_config())
    print(f"query candidates written: {n}")
