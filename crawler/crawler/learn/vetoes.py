"""Запобіжники перед тим, як кандидат-терм потрапляє в чергу аудиту:
multi-domain support (анти-overfit), PASS-collision (не тягнути gov/media),
abstention (низька впевненість)."""


def survivors(scores, min_domains: int = 3, min_z: float | None = 1.5,
              max_candidates: int = 50, min_pass_docs: int = 0):
    """Gate candidate terms, preserving input order. Additive params default to
    inert so existing callers are byte-identical:
    - min_z=None disables the abstention gate (query miner v2: degenerate z must not gate);
    - max_candidates<=0 means unlimited (v2 "все зразу");
    - min_pass_docs>0 adds an anti-typo hapax guard on raw PASS-doc frequency."""
    out = []
    for s in scores:
        if min_z is not None and s.z < min_z:  # abstention
            continue
        if s.in_neg_anchor:                   # PASS-collision з negative anchor
            continue
        if len({d for d in s.domains if d}) < min_domains:  # multi-domain support
            continue
        if min_pass_docs and s.doc_count < min_pass_docs:   # anti-typo hapax guard
            continue
        out.append(s)
        if 0 < max_candidates <= len(out):
            break
    return out
