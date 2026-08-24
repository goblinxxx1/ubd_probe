from crawler.judge.base import Verdict, NullJudge


def test_verdict_fields():
    v = Verdict(genuine=True, page_scoped=False, reason="site banner")
    assert v.genuine is True and v.page_scoped is False and v.reason == "site banner"


def test_null_judge_always_genuine_and_page_scoped():
    v = NullJudge().verdict(object())
    assert v.genuine is True and v.page_scoped is True
