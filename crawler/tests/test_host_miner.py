# crawler/tests/test_host_miner.py
from crawler.learn.host_miner import mine_hosts


def _row(host, is_article=False, outbound=0, pos=False, url="u"):
    return {"host": host, "label": "pass", "is_article": is_article,
            "outbound_hosts": outbound, "neg_anchor": False, "pos_anchor": pos, "text": url}


def test_article_heavy_host_scores_high_media():
    rows = [_row("blog.ua", is_article=True) for _ in range(4)]
    scores = {s.host: s for s in mine_hosts(rows)}
    assert scores["blog.ua"].media_ratio == 1.0
    assert scores["blog.ua"].support == 4
    assert scores["blog.ua"].provider_evidence is False


def test_aggregator_host_scores_high_aggregator():
    rows = [_row("portal.ua", outbound=5) for _ in range(3)]
    s = {x.host: x for x in mine_hosts(rows)}["portal.ua"]
    assert s.aggregator_ratio == 1.0


def test_provider_like_host_has_evidence_and_low_ratios():
    rows = [_row("shop.ua", pos=True, outbound=0) for _ in range(3)]
    s = {x.host: x for x in mine_hosts(rows)}["shop.ua"]
    assert s.provider_evidence is True
    assert s.media_ratio == 0.0 and s.aggregator_ratio == 0.0
