"""Запобіжники перед тим, як кандидат-терм потрапляє в чергу аудиту:
multi-domain support (анти-overfit), PASS-collision (не тягнути gov/media),
abstention (низька впевненість)."""


def survivors(scores, min_domains: int = 3, min_z: float = 1.5,
              max_candidates: int = 50):
    out = []
    for s in scores:
        if s.z < min_z:                       # abstention
            continue
        if s.in_neg_anchor:                   # PASS-collision з negative anchor
            continue
        if len({d for d in s.domains if d}) < min_domains:  # multi-domain support
            continue
        out.append(s)
        if len(out) >= max_candidates:
            break
    return out
