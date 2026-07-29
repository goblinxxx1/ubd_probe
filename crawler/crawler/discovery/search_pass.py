from crawler.discovery.query_grid import merge_queries
from crawler.models import SourceCandidate


class SearchPass:
    """One crawl-pass of active search. Each provider plan runs SEQUENTIALLY over its
    own grid slice (distinct chunks via independent cursors); a plan's cursor advances
    only if that provider succeeded (advance-on-success). No threads — shared state is
    not thread-safe."""

    def __init__(self, plans, state, grid, queries_per_pass, static_keywords=None):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._n = queries_per_pass
        self._pins = list(static_keywords or [])

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        for plan in self._plans:
            start = self._start_for(plan.cursor_key)
            batch, new_cursor = self._grid.next_batch(self._n, start)
            pins = self._pins if plan.include_pins else []
            keywords = merge_queries(batch, pins)
            plan.reset()
            out.extend(plan.discovery.run(keywords, known))
            if plan.succeeded():
                self._set_cursor(plan.cursor_key, new_cursor)
        return out

    def provider_for_site_query(self):
        """DDG plan's ActiveDiscovery for `site:` queries (falls back to first plan)."""
        for plan in self._plans:
            if plan.cursor_key == "grid_cursor":
                return plan.discovery
        return self._plans[0].discovery if self._plans else None

    def _start_for(self, cursor_key: str) -> int:
        if cursor_key == "searxng_cursor":
            c = self._state.searxng_cursor
            return c if c >= 0 else len(self._grid) // 2
        return self._state.grid_cursor

    def _set_cursor(self, cursor_key: str, value: int) -> None:
        if cursor_key == "searxng_cursor":
            self._state.set_searxng_cursor(value)
        else:
            self._state.set_grid_cursor(value)
