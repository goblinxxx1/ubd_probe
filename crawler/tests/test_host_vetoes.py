from crawler.learn.host_miner import HostScore
from crawler.learn.host_vetoes import survivors


def _s(host, media=0.9, aggr=0.0, support=4, provider=False):
    return HostScore(host=host, media_ratio=media, aggregator_ratio=aggr,
                     support=support, provider_evidence=provider)


def test_keeps_media_host():
    assert [s.host for s in survivors([_s("blog.ua")], protected_hosts=set())] == ["blog.ua"]


def test_vetoes_low_support_and_provider_and_protected():
    scores = [_s("a.ua", support=1), _s("b.ua", provider=True),
              _s("c.ua"), _s("d.ua", media=0.1, aggr=0.1)]
    keep = survivors(scores, protected_hosts={"c.ua"})
    assert [s.host for s in keep] == []          # a low-support, b provider, c protected, d below thresholds


def test_vetoes_already_blocked(monkeypatch):
    import crawler.learn.host_vetoes as hv
    monkeypatch.setattr(hv, "is_blocked_host", lambda h: h == "nv.ua")
    assert [s.host for s in survivors([_s("nv.ua"), _s("new.ua")], protected_hosts=set())] == ["new.ua"]
