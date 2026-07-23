"""Офлайн per-host агрегація корпусу: оцінити, наскільки host поводиться як
медіа/агрегатор (article-частка, outbound-spread) проти provider-evidence
(Offer-schema / single-business). Детерміновано; вихід → аудит-черга backend."""

from dataclasses import dataclass, field


@dataclass
class HostScore:
    host: str
    media_ratio: float
    aggregator_ratio: float
    support: int
    provider_evidence: bool
    sample_urls: list = field(default_factory=list)


def mine_hosts(rows, aggregator_min_outbound: int = 3) -> list[HostScore]:
    agg: dict[str, dict] = {}
    for r in rows:
        host = (r.get("host") or "").strip().lower()
        if not host:
            continue
        a = agg.setdefault(host, {"n": 0, "article": 0, "aggr": 0, "provider": 0, "samples": []})
        a["n"] += 1
        if r.get("is_article"):
            a["article"] += 1
        if int(r.get("outbound_hosts", 0)) >= aggregator_min_outbound:
            a["aggr"] += 1
        if r.get("pos_anchor") and int(r.get("outbound_hosts", 0)) == 0:
            a["provider"] += 1
        if len(a["samples"]) < 3 and r.get("url"):
            a["samples"].append(r["url"])
    out = []
    for host, a in agg.items():
        n = a["n"]
        out.append(HostScore(
            host=host,
            media_ratio=a["article"] / n,
            aggregator_ratio=a["aggr"] / n,
            support=n,
            provider_evidence=a["provider"] > 0,
            sample_urls=list(a["samples"]),
        ))
    out.sort(key=lambda s: (-(s.media_ratio + s.aggregator_ratio), s.host))
    return out
