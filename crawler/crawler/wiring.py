import httpx

from crawler.accounts.pool import AccountPool
from crawler.api_client import ApiClient
from crawler.discovery.active import ActiveDiscovery
from crawler.discovery.harvest import ActiveHarvester
from crawler.discovery.providers import build_search_provider
from crawler.extract.base import get_extractor
from crawler.fetchers.facebook import FacebookFetcher
from crawler.fetchers.instagram import InstagramFetcher
from crawler.fetchers.telegram import TelegramFetcher
from crawler.fetchers.website import WebsiteFetcher
from crawler.ratelimit import RateLimiter
from crawler.runner import Runner

_UA = "Mozilla/5.0 (compatible; UBDCrawler/0.1; +https://ubd.example)"


def _http_client(timeout: float, proxy: str | None = None) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": _UA},
                        proxy=proxy, follow_redirects=True)


def build_runner(config) -> Runner:
    api = ApiClient(config.internal_api_url, config.crawler_api_key, config.request_timeout)

    web_client = _http_client(config.request_timeout)
    ig_creds = [c for c in config.bot_accounts if c.platform == "instagram"]
    fb_creds = [c for c in config.bot_accounts if c.platform == "facebook"]
    ig_pool = AccountPool("instagram", ig_creds, api)
    fb_pool = AccountPool("facebook", fb_creds, api)

    fetchers = {
        "website": WebsiteFetcher(web_client),
        "telegram": TelegramFetcher(web_client),
        "instagram": InstagramFetcher(ig_pool, _http_client(config.request_timeout,
                                                             config.proxies.get("instagram"))),
        "facebook": FacebookFetcher(fb_pool, _http_client(config.request_timeout,
                                                          config.proxies.get("facebook"))),
    }
    extractor = get_extractor(config.extractor)
    rate_limiter = RateLimiter(config.min_delay_seconds)

    discovery = None
    harvester = None
    if config.active_discovery:
        provider = build_search_provider(config)
        if provider is not None:
            budget = config.search_budget or len(config.search_keywords)
            discovery = ActiveDiscovery(budget=budget, search_provider=provider)
            if config.active_fetch_budget:
                harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                            fetch_budget=config.active_fetch_budget)
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, keywords=config.search_keywords, harvester=harvester,
                  freshness_ttl_days=config.freshness_ttl_days)
