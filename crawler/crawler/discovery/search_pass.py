from crawler.discovery.query_grid import merge_queries
from crawler.models import SourceCandidate


class SearchPass:
    """One crawl-pass of active search over a single provider. With ttl_seconds>0 it
    DUE-WALKS: from grid_cursor it collects up to block_size cache-stale phrases,
    skipping still-fresh ones, so every pass does fresh network work and the walk
    self-aligns to the cache TTL. ttl_seconds=0 => plain contiguous block walk.
    Advance-on-success: the cursor moves past all scanned phrases only if the pass
    succeeded (a throttled/backed-off pass re-scans the same phrases next time)."""

    def __init__(self, plans, state, grid, block_size, static_keywords=None,
                 ttl_seconds=0.0):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._bs = block_size
        self._pins = list(static_keywords or [])
        self._ttl = ttl_seconds

    def set_grid(self, grid) -> None:
        """Swap in a freshly rebuilt grid (after in-loop learning). The rotation
        cursor lives in persistent state (`grid_cursor`), not here, so a swap never
        loses position — next_batch wraps modulo the new length."""
        self._grid = grid

    def drain(self) -> list[SourceCandidate]:
        """Step 1 in isolation: re-surface cached-but-unharvested candidates. No network,
        does not touch grid_cursor — safe to call during global backoff when the DDG search
        leg is skipped. ttl<=0 => no drain (mirrors run())."""
        if self._ttl <= 0:
            return []
        out: list[SourceCandidate] = []
        for _kw, cands in self._state.unharvested(self._ttl):
            out.extend(cands)
        return out

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        size = len(self._grid)
        if size == 0 or not self._plans:
            return out
        # 1) DRAIN once (no re-search): re-surface cached-but-unharvested candidates.
        out.extend(self.drain())
        # 2) Pick the due batch ONCE; every available provider searches the same phrases
        #    (cross-provider redundancy raises recall).
        cursor = self._state.grid_cursor
        if self._ttl > 0:
            batch, new_cursor = self._collect_due(cursor, size)
        else:
            batch, new_cursor = self._grid.next_batch(self._bs, cursor)
        any_success = False
        for plan in self._plans:
            if not plan.available():
                continue
            pins = self._pins if plan.include_pins else []
            keywords = merge_queries(batch, pins)
            searched = plan.discovery.run(keywords, known)
            for c in searched:
                if c.origin_key is None and c.discovery_note and ": " in c.discovery_note:
                    c.origin_key = c.discovery_note.split(": ", 1)[1]
            out.extend(searched)
            if plan.succeeded():
                any_success = True
        # advance the cursor only if at least one provider covered this batch
        if any_success:
            self._state.set_grid_cursor(new_cursor)
        return out

    def _collect_due(self, cursor, size):
        """Scan forward from cursor collecting up to block_size due (stale/unseen)
        phrases; return (batch, next_cursor). next_cursor is past every phrase
        scanned (fresh skipped ones included), wrapping modulo size."""
        batch: list[str] = []
        scanned = 0
        while scanned < size and len(batch) < self._bs:
            kw = self._grid.at(cursor)
            if not self._state.is_fresh(kw, self._ttl):
                batch.append(kw)
            cursor = (cursor + 1) % size
            scanned += 1
        return batch, cursor

    def any_provider_available(self) -> bool:
        return any(p.available() for p in self._plans)

    def provider_for_site_query(self):
        """ActiveDiscovery of the first currently-available provider (health-aware), or None.
        Under DDG backoff this returns the SearXNG discovery so the site: leg still runs."""
        for plan in self._plans:
            if plan.available():
                return plan.discovery
        return None
