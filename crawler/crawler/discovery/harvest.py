import logging

from crawler.discovery.attribution import attribute, build_page_ctx, _outbound_hosts
from crawler.discovery.blocklist import is_blocked_host
from crawler.discovery.host_quality import is_low_value_host, is_news_host
from crawler.util.text_lang import is_non_ukrainian
from crawler.discovery.brand_feed import _host
from crawler.discovery.passive import normalize_ref
from crawler.discovery.promo_lexicon import seed_is_target
from crawler.discovery.source_hint import business_domains_from_page
from crawler.extract.aggregate import aggregate_page
from crawler.extract.categories import resolve_offer_categories
from crawler.payloads import offer_payload
from crawler.util.hosts import is_foreign_host, is_ru_by_geo

log = logging.getLogger(__name__)

_FETCHABLE = ("website", "telegram")


def _is_editorial_page(items) -> bool:
    """A news/blog page: declares article/blog markup (schema.org NewsArticle/BlogPosting/
    Article or og:type=article) AND carries no commercial schema (Offer/LocalBusiness/
    Organization). Such a page is never an offer source."""
    if not any(getattr(it, "is_article", False) for it in items):
        return False
    return not any(getattr(it, "has_offer_schema", False)
                   or getattr(it, "has_business_schema", False) for it in items)


class ActiveHarvester:
    def __init__(self, api, fetchers, extractor, rate_limiter, fetch_budget=20,
                 walker=None, domain_rate_limiter=None, corpus_recorder=None,
                 domain_registry=None, hardening_enabled=True,
                 aggregator_min_outbound=3, aggregator_store=None,
                 aggregator_max_domains=500, revisit_cooldown_seconds=0,
                 geo_block_store=None, media_blocker=None, media_autoblock_crawls=2,
                 lang_block_store=None, editorial_gate_enabled=True,
                 source_hint_enabled=True):
        self._api = api
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._budget = fetch_budget
        self._walker = walker
        self._domain_rl = domain_rate_limiter
        self._corpus = corpus_recorder
        self._registry = domain_registry
        self._hardening_enabled = hardening_enabled
        self._aggregator_min_outbound = aggregator_min_outbound
        self._aggregator_store = aggregator_store
        self._aggregator_max_domains = aggregator_max_domains
        self._revisit_cooldown = revisit_cooldown_seconds
        self._geo_block_store = geo_block_store
        self._media_blocker = media_blocker
        self._media_autoblock_crawls = media_autoblock_crawls
        self._lang_block_store = lang_block_store
        self._editorial_gate_enabled = editorial_gate_enabled
        self._source_hint_enabled = source_hint_enabled

    def harvest(self, candidates, cats, known, summary, known_hosts=None) -> int:
        known_hosts = known_hosts or set()
        used = 0
        stop = 0
        for idx, cand in enumerate(candidates):
            if used >= self._budget:
                return idx                    # budget break: idx..end untouched
            stop = idx + 1
            if cand.type not in _FETCHABLE:
                continue
            # Russia/Belarus signal anywhere in the URL — ccTLD/subdomain OR a city-code
            # path segment (restoran.cafe/spb). Never fetch, AND pin the WHOLE host into the
            # persistent geo-block so is_blocked_host drops it from every future feed/walk.
            if cand.type == "website" and is_ru_by_geo(cand.url_or_handle):
                if self._geo_block_store is not None:
                    self._geo_block_store.add(cand.url_or_handle)
                continue
            # UA-only: never fetch/walk a foreign-ccTLD site (напр. .by). Гейт до
            # витрати бюджету й до запису в domain_registry, тож іноземний хост не
            # осідає й не ре-фідиться.
            if cand.type == "website" and is_foreign_host(cand.url_or_handle):
                continue
            # Low-value: інституційні (gov/edu/mil/int) та глобальні платформи ніколи не
            # джерело офера — гейт ДО обходу, щоб не палити бюджет на 88% сміття з видачі.
            if cand.type == "website" and is_low_value_host(cand.url_or_handle):
                continue
            # Новинний хост (news/novyny/gazeta/… у мітці) — медіа, не джерело офера;
            # гейт ДО обходу, щоб не краулити новини (groza-news.info тощо).
            if cand.type == "website" and is_news_host(cand.url_or_handle):
                continue
            # Блокліст = не краулити взагалі: заблокований хост ніколи не фетчиться/
            # не обходиться (не лише «не приписувати як провайдера»).
            if cand.type == "website" and is_blocked_host(cand.url_or_handle):
                continue
            # Revisit-cooldown: не ре-краулити домен, бачений у межах вікна cooldown
            # (belt для фідів, крім DomainFeed/site:, що вже фільтрують через top()).
            if (cand.type == "website" and self._revisit_cooldown and self._registry is not None
                    and self._registry.seen_within(_host(cand.url_or_handle), self._revisit_cooldown)):
                continue
            if normalize_ref(cand.type, cand.url_or_handle) in known:
                continue
            if (cand.type == "website" and not cand.bypass_host_skip
                    and _host(cand.url_or_handle) in known_hosts):
                continue
            fetcher = self._fetchers.get(cand.type)
            if fetcher is None:
                continue
            used += 1
            before_o, before_e = summary["offers"], summary["errors"]
            structural = False
            try:
                structural = self._harvest_one(cand, fetcher, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — isolate per candidate
                summary["errors"] += 1
                log.warning("active harvest failed for %s: %s", cand.url_or_handle, exc)
            if self._registry is not None and cand.type == "website":
                host = _host(cand.url_or_handle)
                self._registry.record(host, summary["offers"] - before_o,
                                      summary["errors"] - before_e,
                                      structural_provider=structural)
                if (self._media_blocker is not None
                        and self._registry.media_block_due(host, self._media_autoblock_crawls)):
                    if self._media_blocker.block(host, cand.url_or_handle):
                        self._registry.mark_media_blocked(host)
        return stop

    def _select_fetch_set(self, candidates, known, known_hosts):
        """Фаза 1 (серійна): застосувати чисті skip-гейти в порядку (з їх in-scan
        side-ефектами: geo_block.add) і відібрати кандидатів на fetch, обмежившись
        бюджетом. `selected_hosts` точно відтворює серійну same-host `seen_within`-
        супресію без реальних fetch'ів. Повертає (ordered_fetch, stop), де stop —
        той самий індекс, що й серійний harvest."""
        used = 0
        stop = 0
        selected = []
        selected_hosts = set()
        for idx, cand in enumerate(candidates):
            if used >= self._budget:
                return selected, idx          # budget break: idx..end untouched
            stop = idx + 1
            if cand.type not in _FETCHABLE:
                continue
            if cand.type == "website" and is_ru_by_geo(cand.url_or_handle):
                if self._geo_block_store is not None:
                    self._geo_block_store.add(cand.url_or_handle)
                continue
            if cand.type == "website" and is_foreign_host(cand.url_or_handle):
                continue
            if cand.type == "website" and is_low_value_host(cand.url_or_handle):
                continue
            if cand.type == "website" and is_news_host(cand.url_or_handle):
                continue
            if cand.type == "website" and is_blocked_host(cand.url_or_handle):
                continue
            host = _host(cand.url_or_handle) if cand.type == "website" else None
            if (cand.type == "website" and self._revisit_cooldown and self._registry is not None
                    and (self._registry.seen_within(host, self._revisit_cooldown)
                         or host in selected_hosts)):
                continue
            if normalize_ref(cand.type, cand.url_or_handle) in known:
                continue
            if (cand.type == "website" and not cand.bypass_host_skip
                    and host in known_hosts):
                continue
            if self._fetchers.get(cand.type) is None:
                continue
            used += 1
            selected.append(cand)
            if host is not None:
                selected_hosts.add(host)
        return selected, stop

    def _plan(self, cand):
        """(urls, domain, delay, foreign) for a candidate. Website candidates expand via
        the walker; without a walker, a website candidate is fetched only if root-or-target."""
        if self._walker is not None and cand.type == "website":
            plan = self._walker.walk(cand)
            return plan.urls, plan.domain, plan.crawl_delay, plan.foreign
        if cand.type == "website" and not seed_is_target(cand.url_or_handle):
            return [], None, None, False
        return [cand.url_or_handle], None, None, False

    def _wait(self, cand_type, domain, delay) -> None:
        if domain is not None and self._domain_rl is not None:
            self._domain_rl.wait(domain, delay)
        elif self._rl is not None:
            self._rl.wait(cand_type)

    def _harvest_one(self, cand, fetcher, cats, known, summary) -> bool:
        urls, domain, delay, foreign = self._plan(cand)
        if foreign:
            # Foreign-language domain judged at the homepage (A): pin the whole host so it
            # is never re-walked, and skip its pages entirely.
            if self._lang_block_store is not None:
                self._lang_block_store.add(cand.url_or_handle)
            return False
        structural = False
        for url in urls:
            self._wait(cand.type, domain, delay)
            src = {"id": None, "type": cand.type, "url_or_handle": url, "name": cand.name}
            try:
                items, _ = fetcher.fetch(src, None)
                if is_non_ukrainian(" ".join(it.text or "" for it in items)):
                    # Non-Ukrainian content reached during the walk (B): pin the host, then
                    # abandon the whole domain rather than walk its remaining pages.
                    if self._lang_block_store is not None:
                        self._lang_block_store.add(cand.url_or_handle)
                    break
                if (self._editorial_gate_enabled and not structural
                        and _is_editorial_page(items)):
                    # News/blog portal page with no commercial schema — abandon the whole
                    # domain rather than walk its remaining (all-editorial) pages.
                    break
                if self._process_page(cand, items, cats, known, summary):
                    structural = True
            except Exception as exc:  # noqa: BLE001 — one page must not sink the domain
                summary["errors"] += 1
                log.warning("harvest page failed for %s: %s", url, exc)
        return structural

    def _process_page(self, cand, items, cats, known, summary) -> bool:
        structural_provider = any(
            getattr(it, "has_offer_schema", False) or getattr(it, "has_business_schema", False)
            for it in items)
        passing = []
        for it in items:
            is_offer = self._extractor.extract(it, "", cats) is not None
            if self._corpus is not None:
                self._corpus.record(it, is_offer)
            if is_offer:
                passing.append(it)
        ctx = build_page_ctx(cand, passing)
        if self._aggregator_store is not None and is_blocked_host(ctx.host):
            hosts = _outbound_hosts(passing)
            if hosts:
                self._aggregator_store.add(hosts, self._aggregator_max_domains)
        collected = []
        for item in passing:
            attr = attribute(item, ctx, hardening_enabled=self._hardening_enabled,
                             aggregator_min_outbound=self._aggregator_min_outbound)
            if attr is None:
                continue
            offer = self._extractor.extract(item, attr.provider, cats)
            collected.append((offer, attr))
        if not collected:
            return structural_provider
        groups, order = {}, []
        for offer, attr in collected:
            key = offer.article_url
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(offer)
        for key in order:
            page_offer = aggregate_page(groups[key])
            page_offer.offer_category_ids = resolve_offer_categories(
                self._api, cats, page_offer.offer_category_matches)
            self._api.submit_offer(offer_payload(page_offer))
            summary["offers"] += 1
        for _, attr in collected:
            if attr.suggest_url_or_handle:
                s_ref = normalize_ref(attr.suggest_type, attr.suggest_url_or_handle)
                if s_ref not in known:
                    self._api.submit_suggestion({
                        "name": attr.suggest_name,
                        "type": attr.suggest_type,
                        "url_or_handle": attr.suggest_url_or_handle,
                        "discovered_from_source_id": None,
                        "discovery_note": f"active-search offer from {cand.url_or_handle}",
                    })
                    known.add(s_ref)
                    summary["suggestions"] += 1
        if self._source_hint_enabled:
            # An afisha/listing page re-posts a business's offer; mine the business's own
            # domain from its contact email and suggest it as a source so the real business
            # is crawled directly (rather than attributing the offer to the listing).
            for hint in business_domains_from_page(items, ctx.host):
                ref = normalize_ref("website", hint)
                if ref not in known:
                    self._api.submit_suggestion({
                        "name": hint, "type": "website",
                        "url_or_handle": f"https://{hint}",
                        "discovered_from_source_id": None,
                        "discovery_note": f"business email domain on {cand.url_or_handle}",
                    })
                    known.add(ref)
                    summary["suggestions"] += 1
        return structural_provider
