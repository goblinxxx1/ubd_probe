"""Запобіжники перед аудит-чергою host-кандидатів: мін support; must look media/aggregator;
не provider-evidence; не protected (активні sources / domain-rating-productive); не вже-blocked."""

from crawler.discovery.blocklist import is_blocked_host
from crawler.util.hosts import bare_host


def survivors(scores, *, protected_hosts, min_support: int = 3, media_min: float = 0.5,
              aggregator_min: float = 0.5, max_candidates: int = 50):
    protected = {bare_host(h) for h in (protected_hosts or set())}
    out = []
    for s in scores:
        if s.support < min_support:
            continue
        if s.provider_evidence:
            continue
        if s.media_ratio < media_min and s.aggregator_ratio < aggregator_min:
            continue
        if s.host in protected or is_blocked_host(s.host):
            continue
        out.append(s)
        if len(out) >= max_candidates:
            break
    return out
