from crawler.learn.miner import TermScore
from crawler.learn.vetoes import survivors


def _ts(term, z, domains, neg=False):
    return TermScore(term=term, z=z, pass_count=len(domains), fail_count=0,
                     domains=set(domains), in_neg_anchor=neg)


def test_multi_domain_support_required():
    ok = _ts("уцінка", 3.0, ["a.ua", "b.ua", "c.ua"])
    weak = _ts("рідкість", 3.0, ["a.ua"])
    out = survivors([ok, weak], min_domains=3, min_z=1.5)
    terms = {s.term for s in out}
    assert "уцінка" in terms and "рідкість" not in terms


def test_pass_collision_and_abstention():
    collide = _ts("розклад", 3.0, ["a.ua", "b.ua", "c.ua"], neg=True)
    lowz = _ts("може", 0.5, ["a.ua", "b.ua", "c.ua"])
    out = survivors([collide, lowz], min_domains=3, min_z=1.5)
    assert out == []
