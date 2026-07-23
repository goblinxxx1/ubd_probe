# crawler/tests/test_site_query.py
from crawler.discovery.site_query import SITE_INTENT_FORMS, SiteQueryPlanner


def _planner():
    return SiteQueryPlanner(terms=("знижка", "акція"))


def test_builds_site_prefixed_query_per_domain():
    batch, cur = _planner().next_batch(["a.ua", "b.ua"], budget=5, cursor=0)
    assert batch == ["site:a.ua знижка", "site:b.ua акція"]   # different term per domain index
    assert cur == 1                                            # phase advanced by 1


def test_budget_caps_domain_count():
    batch, _ = _planner().next_batch(["a.ua", "b.ua", "c.ua"], budget=2, cursor=0)
    assert batch == ["site:a.ua знижка", "site:b.ua акція"]    # third domain dropped


def test_cursor_phase_rotates_terms_between_passes():
    batch, cur = _planner().next_batch(["a.ua"], budget=5, cursor=1)
    assert batch == ["site:a.ua акція"]                        # cursor=1 → terms[1]
    assert cur == 0                                            # (1 + 1) % 2


def test_empty_and_none_domains_filtered():
    batch, _ = _planner().next_batch(["a.ua", "", None, "b.ua"], budget=5, cursor=0)
    assert batch == ["site:a.ua знижка", "site:b.ua акція"]    # indices on filtered list


def test_empty_terms_is_safe():
    batch, cur = SiteQueryPlanner(terms=()).next_batch(["a.ua"], budget=5, cursor=3)
    assert batch == [] and cur == 3


def test_default_terms_nonempty_and_deterministic():
    p = SiteQueryPlanner()
    assert "знижка" in SITE_INTENT_FORMS and len(SITE_INTENT_FORMS) == 7
    assert p.next_batch(["a.ua"], 5, 0) == p.next_batch(["a.ua"], 5, 0)
