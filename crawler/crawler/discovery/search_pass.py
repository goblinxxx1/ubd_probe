from crawler.discovery.query_grid import merge_queries
from crawler.models import SourceCandidate
from crawler.util.hosts import bare_host


class SearchPass:
    """One crawl-pass of active search over a single provider. With ttl_seconds>0 it
    DUE-WALKS: from grid_cursor it collects up to block_size cache-stale phrases,
    skipping still-fresh ones, so every pass does fresh network work and the walk
    self-aligns to the cache TTL. ttl_seconds=0 => plain contiguous block walk.
    Advance-on-success: the cursor moves past all scanned phrases only if the pass
    succeeded (a throttled/backed-off pass re-scans the same phrases next time)."""

    def __init__(self, plans, state, grid, block_size, static_keywords=None,
                 ttl_seconds=0.0, page_cap=1, breed_sink=None, promote_min=2,
                 protected_terms=frozenset(),
                 cold_tries=3, mult_cap=8.0, alpha=0.3):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._bs = block_size
        self._pins = list(static_keywords or [])
        self._ttl = ttl_seconds
        self._page_cap = max(1, int(page_cap))
        # Задача 5C: людський override. Захищені фрази (адмін-помічені `protected`)
        # НІКОЛИ не авто-ретайряться — завжди отримують базовий TTL, попри dry-streak
        # у phrase_stats. Рішення людини виграє в автомата.
        self._protected_terms = frozenset(protected_terms or ())
        # Задача 5B: reward-driven розмноження термів. breed_sink(term) — callback
        # (зазвичай зі wiring), що додає термін у пул кандидатів майнера, сам
        # відсіюючи відхилені людиною (людський reject виграє). None = вимкнено.
        self._breed_sink = breed_sink
        self._promote_min = promote_min
        # Задача 6: конфігуровані тюнінги адаптивного планувальника фраз
        # (раніше — жорсткі дефолти effective_ttl/record_yield).
        self._cold_tries = cold_tries
        self._mult_cap = mult_cap
        self._alpha = alpha
        # Задача 8: саморозказана продуктивність (new_domains, queries) з ОСТАННЬОГО
        # run() — сирі числа для гейджа new/query, що runner.py логує поруч із
        # saturation-гейджем Задачі 7 (без ручного порівняння baseline).
        self._last_new_domains = 0
        self._last_queries = 0

    def set_protected_terms(self, terms) -> None:
        """Задача 5C: живий перемикач захисту (без рестарту краулера) — той самий
        періодичний tick, що рефрешить грід з approved-термів, підміняє й цю
        множину, щойно адмін позначив/зняв `protected` у бекенді."""
        self._protected_terms = frozenset(terms or ())

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

    def last_productivity(self) -> tuple[int, int]:
        """Задача 8: (new_domains, queries) останнього run() — used by runner.py
        для self-reported active productivity gauge (new/query)."""
        return (self._last_new_domains, self._last_queries)

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        size = len(self._grid)
        if size == 0 or not self._plans:
            self._last_new_domains = 0
            self._last_queries = 0
            return out
        # 1) DRAIN once (no re-search): re-surface cached-but-unharvested candidates.
        out.extend(self.drain())
        # 2) Pick the due batch ONCE; every available provider searches the same phrases
        #    (cross-provider redundancy raises recall). Each phrase carries its SERP page.
        cursor = self._state.grid_cursor
        if self._ttl > 0:
            batch, new_cursor = self._collect_due(cursor, size)
        else:
            batch, new_cursor = self._grid.next_batch(self._bs, cursor)
        pages = {p: self._state.current_page(p) for p in batch}
        # cache-note suffix ("ddg-cache: <key>") and fresh-note suffix ("ddg:..: <phrase>")
        # both attribute back to the batch phrase, so per-phrase yield can be counted.
        attribution = {}
        for p in batch:
            attribution[p] = p
            attribution[self._state._key(p, pages[p])] = p
        new_by_phrase: dict[str, int] = {p: 0 for p in batch}
        # Phrases whose search channel genuinely responded across ANY plan this pass.
        # A censored phrase (block/backoff/error on every plan) is a missing observation,
        # not a zero, so it is excluded from productivity accounting below. A discovery
        # that does not report served phrases (older/fake) defaults to the whole batch.
        served: set[str] = set()
        any_success = False
        for plan in self._plans:
            if not plan.available():
                continue
            pins = self._pins if plan.include_pins else []
            keywords = merge_queries(batch, pins)
            disc = plan.discovery
            searched = disc.run(keywords, known, pages)
            served |= getattr(disc, "last_served_phrases", set(batch))
            for c in searched:
                suffix = (c.discovery_note.split(": ", 1)[1]
                          if c.discovery_note and ": " in c.discovery_note else None)
                phrase = attribution.get(suffix) if suffix else None
                if phrase is not None:                      # a grid-phrase result (not a pin)
                    new_by_phrase[phrase] += 1              # run() already known-filtered → new
                    c.origin_key = self._state._key(phrase, pages[phrase])   # exact harvest key
                elif c.origin_key is None and suffix:
                    c.origin_key = suffix
            out.extend(searched)
            if plan.succeeded():
                any_success = True
        # Задача 8: продуктивність цього циклу — незалежно від any_success, бо
        # new_by_phrase уже відображає фактично знайдені нові кандидати за батч.
        self._last_new_domains = sum(new_by_phrase.values())
        self._last_queries = len(batch)
        # advance the grid cursor AND each phrase's page cursor only on a covered batch
        if any_success:
            for p in batch:
                if p in served:            # censored phrase: never saw a page → don't advance it
                    self._state.record_page_result(p, pages[p], new_by_phrase[p], self._page_cap)
            # Fix 2: батч-запис — ОДИН _save() на прохід замість одного на фразу
            # (record_yield) чи одного на кандидата (note_host), що раніше давало
            # O(batch)/O(candidates) перезаписів файлу стану за прохід.
            # Censored phrases excluded: a missing observation must not decay EWMA/dry_streak.
            self._state.record_yields({p: new_by_phrase[p] for p in batch if p in served},
                                      alpha=self._alpha)                          # NEW: productivity
            self._state.note_hosts([bare_host(c.url_or_handle) for c in out])    # NEW: recapture freq
            if self._breed_sink is not None:
                # Задача 5B (ADD-половина): продуктивна фраза (>=promote_min нових
                # кандидатів за цей прохід) розсіює сервіс-терми зі своїх переможних
                # назв назад у пул кандидатів майнера. Сінк (wiring) сам відсіює
                # відхилені людиною терми — людський reject виграє.
                from crawler.learn.tokenize import service_terms
                winners_by_phrase: dict[str, list[str]] = {p: [] for p in batch}
                for c in out:
                    suffix = (c.discovery_note.split(": ", 1)[1]
                             if c.discovery_note and ": " in c.discovery_note else None)
                    phrase = attribution.get(suffix) if suffix else None
                    if phrase is not None:
                        winners_by_phrase.setdefault(phrase, []).append(c.name or "")
                for p in batch:
                    if new_by_phrase[p] >= self._promote_min:
                        for name in winners_by_phrase.get(p, []):
                            for term in service_terms(name):
                                self._breed_sink(term)
            self._state.set_grid_cursor(new_cursor)
        return out

    def _collect_due(self, cursor, size):
        """Scan forward from cursor collecting up to block_size due phrases; a phrase is
        due when its CURRENT SERP page is not cache-fresh UNDER ITS ADAPTIVE TTL. Dry
        phrases carry a longer effective TTL, so the walk self-concentrates on productive
        ones. next_cursor is past every phrase scanned (fresh skipped included), wrapping."""
        batch: list[str] = []
        scanned = 0
        while scanned < size and len(batch) < self._bs:
            kw = self._grid.at(cursor)
            ttl = self._effective_ttl_for(kw)
            if not self._state.is_fresh(kw, ttl, self._state.current_page(kw)):
                batch.append(kw)
            cursor = (cursor + 1) % size
            scanned += 1
        return batch, cursor

    def _effective_ttl_for(self, kw: str) -> float:
        """Adaptive freshness-TTL для фрази, з людським override. Захищена фраза
        завжди отримує базовий TTL (ніколи не душиться беком), решта — делегує
        адаптивний backoff у SearchState (сухі фрази = довший TTL).

        `protected_terms` містить ГОЛІ адмін-терми (напр. "евакуатор"), а `kw`
        тут — уже СКЛАДЕНА grid-фраза ("евакуатор знижка військовим"), бо
        build_grid завжди клеїть "{service} {modifier} {audience}" /
        "{service} {audience}" — сервіс-терм ніколи не є окремим grid-входом.
        Тому точний membership-чек ніколи б не спрацював у проді. Захищено, якщо
        kw ТОЧНО дорівнює захищеному терму, АБО захищений терм — його провідний
        ПОВНОСЛІВНИЙ префікс (бо композиція завжди ставить сервіс першим)."""
        kw_norm = (kw or "").strip().casefold()
        for p in self._protected_terms:
            p_norm = (p or "").strip().casefold()
            if p_norm and (kw_norm == p_norm or kw_norm.startswith(p_norm + " ")):
                return self._ttl                   # human-protected: never suppressed
        return self._state.effective_ttl(kw, self._ttl,
                                          cold_tries=self._cold_tries, mult_cap=self._mult_cap)

    def any_provider_available(self) -> bool:
        return any(p.available() for p in self._plans)

    def provider_for_site_query(self):
        """ActiveDiscovery of the first currently-available provider (health-aware), or None.
        Under DDG backoff this returns the SearXNG discovery so the site: leg still runs."""
        for plan in self._plans:
            if plan.available():
                return plan.discovery
        return None
