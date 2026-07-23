# crawler/crawler/discovery/site_query.py
"""Offline generator for narrow per-domain `site:` search queries.

For a productive/partner domain, ask the search engine which promo pages it indexes
that our sitemap/BFS walker missed — via `site:{domain} {intent-term}`. Audience is
intentionally absent: the domain constrains scope and the downstream relevance-gate
enforces audience (recall here, precision there). Deterministic, stable order."""

# Curated intent surface forms (no audience, no gov/NGO-program noise).
SITE_INTENT_FORMS = (
    "знижка", "акція", "промокод", "спеціальна ціна", "пільгова ціна",
    "спеціальна пропозиція", "сертифікат",
)


class SiteQueryPlanner:
    """One rotating intent term per domain; the cursor rotates the term phase per pass."""

    def __init__(self, terms=SITE_INTENT_FORMS):
        self._terms = tuple(terms)

    def next_batch(self, domains, budget, cursor):
        if not self._terms:
            return [], cursor
        doms = [d for d in domains if d][:max(0, int(budget))]
        out = [f"site:{d} {self._terms[(cursor + i) % len(self._terms)]}"
               for i, d in enumerate(doms)]
        return out, (cursor + 1) % len(self._terms)
