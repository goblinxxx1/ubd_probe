from crawler.discovery.query_grid import merge_queries
from crawler.models import SourceCandidate


class SearchPass:
    """One crawl-pass of active search over a single provider. Walks a block of
    `block_size` grid phrases from `grid_cursor`, advancing the cursor by block_size
    on success (advance-on-success keeps a throttled/backed-off pass from skipping
    phrases). Sequential; the inter-pass sleep dominates wall-clock."""

    def __init__(self, plans, state, grid, block_size, static_keywords=None):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._bs = block_size
        self._pins = list(static_keywords or [])

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        size = len(self._grid)
        if size == 0 or not self._plans:
            return out
        plan = self._plans[0]
        cursor = self._state.grid_cursor
        batch, new_cursor = self._grid.next_batch(self._bs, cursor)
        pins = self._pins if plan.include_pins else []
        keywords = merge_queries(batch, pins)
        out.extend(plan.discovery.run(keywords, known))
        if plan.succeeded():
            self._state.set_grid_cursor(new_cursor)
        return out

    def provider_for_site_query(self):
        """The single provider's ActiveDiscovery for `site:` queries."""
        return self._plans[0].discovery if self._plans else None
