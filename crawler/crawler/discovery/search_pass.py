from crawler.discovery.query_grid import merge_queries
from crawler.models import SourceCandidate


class SearchPass:
    """One crawl-pass of active search. Providers search DISJOINT adjacent blocks of the
    grid (no overlap → together cover N blocks/pass) and SWAP blocks each cycle, so a block
    one engine missed is searched by the other next cycle. Sequential (no threads — shared
    state is not thread-safe; the 2h inter-pass sleep dominates wall-clock anyway)."""

    def __init__(self, plans, state, grid, block_size, static_keywords=None):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._bs = block_size
        self._pins = list(static_keywords or [])

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        size = len(self._grid)
        n = len(self._plans)
        if size == 0 or n == 0:
            return out
        cursor = self._state.block_cursor
        cycle = self._state.cycle
        any_ok = False
        for i, plan in enumerate(self._plans):
            start = (cursor + ((i + cycle) % n) * self._bs) % size   # per-cycle provider↔block swap
            batch, _ = self._grid.next_batch(self._bs, start)
            pins = self._pins if plan.include_pins else []
            keywords = merge_queries(batch, pins)
            plan.reset()
            out.extend(plan.discovery.run(keywords, known))
            if plan.succeeded():
                any_ok = True
        if any_ok:
            new_cursor = cursor + n * self._bs
            if new_cursor >= size:
                new_cursor %= size
                self._state.set_cycle(cycle + 1)
            self._state.set_block_cursor(new_cursor)
        return out

    def provider_for_site_query(self):
        """DDG plan's ActiveDiscovery for `site:` queries (falls back to first plan)."""
        for plan in self._plans:
            if plan.cursor_key == "grid_cursor":
                return plan.discovery
        return self._plans[0].discovery if self._plans else None
