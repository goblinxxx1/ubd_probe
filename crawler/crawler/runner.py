import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import zip_longest

from crawler.discovery.blocklist import is_blocked_host
from crawler.discovery.brand_feed import _host
from crawler.discovery.passive import extract_source_candidates, normalize_ref
from crawler.extract.aggregate import aggregate_page
from crawler.extract.base import CategoryIndex
from crawler.extract.categories import resolve_offer_categories
from crawler.judge.base import NullJudge
from crawler.judge.gate import RelevanceGate
from crawler.models import SourceCandidate
from crawler.payloads import offer_payload, suggestion_payload
from crawler.util.locked_set import LockedSet

log = logging.getLogger(__name__)


class Runner:
    def __init__(self, api_client, fetchers: dict, extractor, rate_limiter,
                 discovery=None, search_pass=None, harvester=None, brand_feed=None,
                 freshness_ttl_days=30, corpus_recorder=None,
                 walker=None, domain_rate_limiter=None,
                 domain_feed=None, domain_registry=None,
                 domain_evict_min_score=0.1, domain_evict_ttl_seconds=2_592_000.0,
                 site_planner=None, site_state=None, site_query_budget=5,
                 osm_feed=None, aggregator_feed=None,
                 passive_schedule=None, now=time.time, revisit_cooldown_seconds=0,
                 reject_ingestor=None, first_crawl_budget=0,
                 passive_workers=1, executor_factory=None,
                 relevance_gate=None, bred_terms=None):
        self._api = api_client
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._discovery = discovery            # retained ONLY for site: queries
        self._search_pass = search_pass
        self._harvester = harvester
        self._brand_feed = brand_feed
        self._freshness_ttl_days = freshness_ttl_days
        self._corpus = corpus_recorder
        self._walker = walker
        self._domain_rl = domain_rate_limiter
        self._domain_feed = domain_feed
        self._domain_registry = domain_registry
        self._evict_min = domain_evict_min_score
        self._evict_ttl = domain_evict_ttl_seconds
        self._site_planner = site_planner
        self._site_state = site_state
        self._site_query_budget = site_query_budget
        self._osm_feed = osm_feed
        self._aggregator_feed = aggregator_feed
        self._passive_schedule = passive_schedule
        self._now = now
        self._revisit_cooldown = revisit_cooldown_seconds
        self._reject_ingestor = reject_ingestor
        self._first_crawl_budget = first_crawl_budget
        self._passive_workers = max(1, int(passive_workers))
        self._executor_factory = executor_factory or (
            lambda mw: ThreadPoolExecutor(max_workers=mw))
        self._gate = relevance_gate or RelevanceGate(NullJudge(), None)
        # Задача 5B: спільна множина reward-breeding термів (наповнює SearchPass.breed_sink
        # у wiring; тут лише прапор, чи є куди зливати — flush() відбувається на learn-тіку).
        self._bred_terms = bred_terms if bred_terms is not None else set()

    def _fetch_for(self, source: dict, last_seen_key):
        fetcher = self._fetchers.get(source["type"])
        if fetcher is None:
            return [], last_seen_key
        self._rl.wait(source["type"])
        return fetcher.fetch(source, last_seen_key)

    @staticmethod
    def _empty_summary() -> dict:
        return {"sources": 0, "offers": 0, "suggestions": 0, "expired": 0, "errors": 0}

    def learn_and_reload_grid(self, config) -> None:
        """Periodic self-learning tick (driven by the scheduler): mine approved
        offers + corpus into the query lexicon, then rebuild the live search grid so
        newly learned service terms take effect WITHOUT a process restart. No-op when
        there's no active search pass. Never raises — learning is best-effort."""
        from crawler.learn.bootstrap_query_lexicon import bootstrap
        from crawler.learn.corpus import CorpusRecorder
        from crawler.wiring import build_query_grid
        if self._search_pass is None:
            return
        recorder = self._corpus or CorpusRecorder(config.corpus_path, config.corpus_max_mb)
        bootstrap(config, self._api, recorder)          # mine → lexicon file + candidates
        self._flush_bred_terms(config)                  # NEW (5B): domix reward-breeding терми
        self._submit_query_candidates(config)           # push candidates to backend audit
        self._search_pass.set_grid(build_query_grid(config))   # rebuild → go live

    def _flush_bred_terms(self, config) -> None:
        """Задача 5B: домішати reward-driven breeding-терми (накопичені SearchPass'ом
        через breed_sink за минулі активні проходи) у файл кандидатів МАЙНЕРА, який
        bootstrap() щойно перезаписав через run_query_miner. Людський reject виграє:
        перевіряємо СВІЖИЙ список відхилених тут теж (термін міг бути відхилений
        МІЖ появою в bred_terms і цим флашем — сінк у wiring перевіряв лише на момент
        додавання). Best-effort: збій бекенда не має топити цикл навчання."""
        if not self._bred_terms:
            return
        path = getattr(config, "query_candidates_path", None)
        if not path:
            self._bred_terms.clear()
            return
        try:
            rejected = {t.strip().casefold()
                       for t in (self._api.list_rejected_query_terms() or ()) if t}
        except Exception:  # noqa: BLE001 — reject-refresh best-effort, як інші learn-тіки
            rejected = set()
        import json
        import os
        try:
            with open(path, encoding="utf-8") as fh:
                cands = json.load(fh)
            if not isinstance(cands, list):
                cands = []
        except (OSError, ValueError):
            cands = []
        have = {c.get("term") for c in cands if isinstance(c, dict)}
        for term in sorted(self._bred_terms):
            if term in rejected or term in have:
                continue
            cands.append({"term": term, "z": 0.0, "support": 1})
            have.add(term)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cands, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        self._bred_terms.clear()

    def _submit_query_candidates(self, config) -> None:
        """Push the just-mined candidates to the backend audit queue so a moderator can
        approve them in the admin (Track A1). Best-effort."""
        import json
        path = getattr(config, "query_candidates_path", None)
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                cands = json.load(fh)
        except (OSError, ValueError):
            return
        items = [{"term": c["term"], "z": c.get("z", 0.0), "support": c.get("support", 0)}
                 for c in (cands or []) if isinstance(c, dict) and c.get("term")]
        if not items:
            return
        try:
            self._api.submit_query_candidates(items)
        except Exception as exc:  # noqa: BLE001 — audit push is best-effort
            log.warning("submit query candidates failed: %s", exc)

    def refresh_grid_from_approved(self, config) -> None:
        """Periodic (~6h) tick: pull moderator-approved query terms from the backend audit
        and rebuild the live grid so they take effect WITHOUT a restart. Best-effort;
        no-op with no active search pass."""
        from crawler.discovery import query_lexicon
        from crawler.wiring import build_query_grid
        if self._search_pass is None:
            return
        try:
            query_lexicon.reload_backend_terms(self._api.list_approved_query_terms())
            self._search_pass.set_grid(build_query_grid(config))
        except Exception as exc:  # noqa: BLE001 — refresh is best-effort
            log.warning("refresh grid from approved failed: %s", exc)

    def search_available(self) -> bool:
        """Whether ANY search provider (DDG or SearXNG) is currently healthy — used by the
        scheduler to decide degraded-vs-full active pass. True when there's no search pass
        at all (nothing to be unavailable)."""
        return self._search_pass.any_provider_available() if self._search_pass is not None else True

    def run(self) -> dict:
        """Active-first orchestration: active discovery runs every loop; the passive
        source-crawl runs only when its (rare) cadence is due. With no passive_schedule
        (tests / one-shot) both run — backward compatible."""
        summary = self.run_active()
        if self._passive_schedule is None or self._passive_schedule.due():
            p = self.run_passive()
            for k in set(summary) | set(p):
                summary[k] = summary.get(k, 0) + p.get(k, 0)
            if self._passive_schedule is not None:
                self._passive_schedule.mark()
        log.info("crawl summary: %s", summary)
        return summary

    def run_active(self, ddg_allowed: bool = True) -> dict:
        """Discovery of NEW domains: feeds + site: + harvester. Never crawls a host that
        is already an active source (published/approved) — passive owns those.

        ddg_allowed=False (global backoff): run everything DDG-INDEPENDENT — the cache
        drain, all four feeds, harvest — and skip only the DDG legs (due-walk search +
        site:). Default True = full pass (byte-identical to before)."""
        self._gate.reset_breaker()
        summary = self._empty_summary()
        if self._harvester is None:
            return summary
        # First-crawl NEW sources FIRST so a heavy discovery harvest can't starve them
        # (first-crawl is DDG-independent; runs in both ddg modes). Self-draining + bounded.
        if self._first_crawl_budget > 0:
            fc = self.run_first_crawl(self._first_crawl_budget)
            for k in fc:
                summary[k] = summary.get(k, 0) + fc[k]
        # Apply moderator-rejection feedback BEFORE feeds read the registry this pass, so a
        # down-ranked domain is already excluded from domain_feed.top() / site: targeting.
        if self._reject_ingestor is not None:
            try:
                self._reject_ingestor.ingest()
            except Exception as exc:  # noqa: BLE001 — feedback must not crash the pass
                summary["errors"] += 1
                log.warning("reject feedback ingest failed: %s", exc)
        cats = CategoryIndex(self._api.list_target_categories(),
                             self._api.list_offer_categories())
        sources = self._api.list_sources(is_active=True)
        # Паралельні задачі фази 2 (ActiveHarvester._execute -> run_one) конкурентно
        # роблять known.add()/x in known -> потрібна потокобезпечна множина.
        known = LockedSet({normalize_ref(s["type"], s["url_or_handle"]) for s in sources})
        try:
            # Unconditional host-skip: active never fetches a host that is already an active
            # website source. Guarantees published/approved sources are left to the passive pass.
            known_hosts = {_host(s["url_or_handle"]) for s in sources if s["type"] == "website"}
            feeds = []
            if self._domain_feed is not None:
                feeds.append(self._domain_feed.candidates(known_hosts))
            if self._search_pass is not None:
                # DDG-independent drain always runs; the DDG due-walk search only when allowed.
                feeds.append(self._search_pass.run(known) if ddg_allowed
                             else self._search_pass.drain())
            if self._brand_feed is not None:
                feeds.append(self._brand_feed.candidates(known))
            if self._osm_feed is not None:
                feeds.append(self._osm_feed.candidates(known))
            if self._aggregator_feed is not None:
                feeds.append(self._aggregator_feed.candidates(known))
            # round-robin interleave so no single feed starves the others under fetch_budget
            candidates = [c for group in zip_longest(*feeds) for c in group if c is not None]
            # site: routes through whichever provider is currently healthy (DDG or SearXNG),
            # so the site: leg survives DDG backoff too.
            site_discovery = (self._search_pass.provider_for_site_query()
                              if self._search_pass is not None else self._discovery)
            # site: only for productive-but-not-yet-approved domains (registry.top excludes
            # known_hosts). No approved-partner arm — passive re-confirms approved sources.
            if (ddg_allowed and self._site_planner is not None and self._site_state is not None
                    and site_discovery is not None and self._domain_registry is not None):
                cur = self._site_state.site_cursor
                reg = [h for h in self._domain_registry.top(
                           self._site_query_budget, known_hosts, self._revisit_cooldown)
                       if not is_blocked_host(h)]   # skip blocklisted + recently-visited hosts
                site_queries, new_cur = self._site_planner.next_batch(
                    reg, self._site_query_budget, cur)
                if site_queries:
                    site_cands = site_discovery.run(site_queries, known)
                    for c in site_cands:
                        c.bypass_host_skip = True
                    candidates += site_cands
                    self._site_state.set_site_cursor(new_cur)
            if candidates:
                stop = self._harvester.harvest(candidates, cats, known, summary,
                                               known_hosts=known_hosts)
                self._mark_consumed_search_phrases(candidates, stop)
        except Exception as exc:  # noqa: BLE001 — discovery must not crash the pass
            summary["errors"] += 1
            log.warning("active discovery / brand-feed harvest failed: %s", exc)
        finally:
            if self._domain_registry is not None:
                try:
                    self._domain_registry.prune(self._evict_min, self._evict_ttl)
                    self._domain_registry.save()
                except Exception as exc:  # noqa: BLE001 — persistence best-effort
                    log.warning("domain registry persist failed: %s", exc)
        return summary

    def run_first_crawl(self, budget) -> dict:
        """Crawl up to `budget` never-crawled active website sources NOW — the same passive
        deep-walk path, but without waiting for the rare passive cadence. DDG-independent. A
        source whose crawl raises is marked attempted (set_crawl_state None) so it drops out of
        'uncrawled' and cannot loop the budget; the next passive cycle re-crawls it fresh."""
        summary = self._empty_summary()
        if budget <= 0:
            return summary
        try:
            sources = self._api.list_uncrawled_sources(budget)
        except Exception as exc:  # noqa: BLE001 — first-crawl must not crash the pass
            summary["errors"] += 1
            log.warning("first-crawl: list uncrawled failed: %s", exc)
            return summary
        if not sources:
            return summary
        cats = CategoryIndex(self._api.list_target_categories(),
                             self._api.list_offer_categories())
        known = {normalize_ref(s["type"], s["url_or_handle"])
                 for s in self._api.list_sources(is_active=True)}
        for source in sources:
            summary["sources"] += 1
            try:
                self._crawl_source(source, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — isolate per source
                summary["errors"] += 1
                log.warning("first-crawl source #%s failed: %s", source.get("id"), exc)
                try:
                    self._api.set_crawl_state(source["id"], None)   # mark attempted -> no loop
                except Exception as exc2:  # noqa: BLE001 — mark is best-effort
                    log.warning("first-crawl mark-attempted #%s failed: %s",
                                source.get("id"), exc2)
        return summary

    def _mark_consumed_search_phrases(self, candidates, stop_index) -> None:
        """Mark a search phrase harvested only when ALL its candidates were examined
        (position < stop_index). Phrases straddling the fetch-budget stay unharvested so
        the next pass drains their remainder — no candidate is orphaned."""
        if stop_index is None:
            return
        state = getattr(self._search_pass, "_state", None)
        if state is None or not hasattr(state, "mark_harvested"):
            return
        last_pos: dict[str, int] = {}
        for i, c in enumerate(candidates):
            key = getattr(c, "origin_key", None)
            if key is not None:
                last_pos[key] = i
        done = [k for k, pos in last_pos.items() if pos < stop_index]
        if done:
            state.mark_harvested(done)

    def run_passive(self) -> dict:
        """Повторно підтверджує approved-джерела (свіжість) + прострочує застарілі source-офери. Виконується на
        рідкому циклі. Джерела краулляться ПАРАЛЕЛЬНО (passive_workers потоків); per-domain
        ввічливість забезпечує per-domain lock усередині DomainRateLimiter. Кожна задача
        накопичує у СВІЙ локальний summary; підсумки зливаються після завершення всіх задач."""
        self._gate.reset_breaker()
        cats = CategoryIndex(self._api.list_target_categories(),
                             self._api.list_offer_categories())
        sources = self._api.list_sources(is_active=True)
        known = LockedSet({normalize_ref(s["type"], s["url_or_handle"]) for s in sources})
        summary = self._empty_summary()

        def crawl_one(source) -> dict:
            local = self._empty_summary()
            local["sources"] += 1
            try:
                self._crawl_source(source, cats, known, local)
            except Exception as exc:  # noqa: BLE001 — isolate per source
                local["errors"] += 1
                log.warning("source #%s failed: %s", source.get("id"), exc)
            return local

        with self._executor_factory(self._passive_workers) as ex:
            futures = [ex.submit(crawl_one, s) for s in sources]
            for fut in as_completed(futures):
                local = fut.result()
                for k in set(summary) | set(local):
                    summary[k] = summary.get(k, 0) + local.get(k, 0)

        try:
            result = self._api.expire_stale(self._freshness_ttl_days)
            summary["expired"] = result.get("expired", 0)
        except Exception as exc:  # noqa: BLE001 — sweep must not crash the pass
            summary["errors"] += 1
            log.warning("expire-stale failed: %s", exc)
        # Persist per-source empty-pass skip counters (armed/decremented above) so the
        # cooldown survives across passes and process restarts.
        if self._domain_registry is not None:
            try:
                self._domain_registry.save()
            except Exception as exc:  # noqa: BLE001 — persistence must not crash the pass
                log.warning("domain registry save (passive) failed: %s", exc)
        return summary

    def _crawl_source(self, source, cats, known, summary):
        # Empty-pass cooldown: a website source that produced 0 offers last time is skipped
        # for its next N crawls (noise/budget saver) — even when it is not blocklisted.
        host = _host(source["url_or_handle"]) if source["type"] == "website" else None
        if host and self._domain_registry is not None and self._domain_registry.take_skip(host):
            summary["skipped_empty"] = summary.get("skipped_empty", 0) + 1
            return
        before_o, before_e = summary["offers"], summary["errors"]
        if self._walker is not None and source["type"] == "website":
            self._crawl_website_deep(source, cats, known, summary)
        else:
            state = self._api.get_crawl_state(source["id"])
            items, new_key = self._fetch_for(source, state.get("last_seen_key"))
            self._process_page(items, source, cats, known, summary)
            self._api.set_crawl_state(source["id"], new_key)
        # Passive path intentionally omits structural_provider and never calls
        # media_block_due: media auto-block is active-only. Relies on active
        # harvest skipping known-source hosts, so a passively-inflated media_streak
        # never reaches an active block decision.
        if host and self._domain_registry is not None:
            self._domain_registry.record(host, summary["offers"] - before_o,
                                         summary["errors"] - before_e)

    def _crawl_website_deep(self, source, cats, known, summary):
        cand = SourceCandidate(name=source["name"], type="website",
                               url_or_handle=source["url_or_handle"])
        plan = self._walker.walk(cand)
        fetcher = self._fetchers.get("website")
        if fetcher is None:
            return
        state = self._api.get_crawl_state(source["id"])
        last_key = state.get("last_seen_key")
        for url in plan.urls:
            try:
                self._domain_rl.wait(plan.domain, plan.crawl_delay)
                page_src = {"id": source["id"], "type": "website",
                            "name": source["name"], "url_or_handle": url}
                items, last_key = fetcher.fetch(page_src, last_key)
                self._process_page(items, source, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — one page must not sink the domain walk
                summary["errors"] += 1
                log.warning("passive deep-walk page failed for %s: %s", url, exc)
        self._api.set_crawl_state(source["id"], last_key)

    def _process_page(self, items, source, cats, known, summary):
        groups, order = {}, []
        for item in items:
            cand = self._extractor.extract(item, source["name"], cats)
            if self._corpus is not None:
                self._corpus.record(item, cand is not None)
            if cand is not None and self._gate.keep(cand):
                key = cand.article_url
                if key not in groups:
                    groups[key] = []
                    order.append(key)
                groups[key].append(cand)
            for sc in extract_source_candidates(item, known):
                # check-then-add по known не атомарний як послідовність під конкурентністю —
                # зрідка можлива дублююча пропозиція; нешкідливо, бекендова черга пропозицій дедупить
                self._api.submit_suggestion(suggestion_payload(sc))
                known.add(normalize_ref(sc.type, sc.url_or_handle))
                summary["suggestions"] += 1
        for key in order:
            page = aggregate_page(groups[key])
            page.offer_category_ids = resolve_offer_categories(
                self._api, cats, page.offer_category_matches)
            self._api.submit_offer(offer_payload(page))
            summary["offers"] += 1
