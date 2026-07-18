from dataclasses import dataclass, field

from pydantic_settings import BaseSettings, SettingsConfigDict

from crawler.models import BotCredential


class _RawSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    internal_api_url: str = "http://localhost:8000"
    crawler_api_key: str = "change-me-crawler-key"
    extractor: str = "heuristic"
    active_discovery: bool = False
    request_timeout: float = 20.0
    min_delay_seconds: float = 2.0
    instagram_accounts: str = ""
    facebook_accounts: str = ""
    proxies: str = ""
    search_providers: str = "duckduckgo"
    search_keywords: str = ""
    search_results_per_keyword: int = 7
    search_min_delay: float = 4.0
    search_budget: int = 0  # 0 = process all keywords
    active_fetch_budget: int = 20
    searxng_url: str = "http://searxng:8080"


@dataclass
class Config:
    internal_api_url: str
    crawler_api_key: str
    extractor: str
    active_discovery: bool
    request_timeout: float
    min_delay_seconds: float
    bot_accounts: list[BotCredential] = field(default_factory=list)
    proxies: dict[str, str] = field(default_factory=dict)
    search_providers: list[str] = field(default_factory=list)
    search_keywords: list[str] = field(default_factory=list)
    search_results_per_keyword: int = 7
    search_min_delay: float = 4.0
    search_budget: int | None = None
    active_fetch_budget: int = 20
    searxng_url: str = "http://searxng:8080"


def _parse_accounts(platform: str, raw: str) -> list[BotCredential]:
    out = []
    for chunk in (c.strip() for c in raw.split(",") if c.strip()):
        username, _, password = chunk.partition(":")
        out.append(BotCredential(platform=platform, username=username, password=password))
    return out


def _split_csv(raw: str) -> list[str]:
    return [c.strip() for c in raw.split(",") if c.strip()]


def _parse_proxies(raw: str) -> dict[str, str]:
    out = {}
    for chunk in (c.strip() for c in raw.split(",") if c.strip()):
        key, _, val = chunk.partition("=")
        out[key.strip()] = val.strip()
    return out


def load_config() -> Config:
    s = _RawSettings()
    accounts = (_parse_accounts("instagram", s.instagram_accounts)
                + _parse_accounts("facebook", s.facebook_accounts))
    return Config(
        internal_api_url=s.internal_api_url,
        crawler_api_key=s.crawler_api_key,
        extractor=s.extractor,
        active_discovery=s.active_discovery,
        request_timeout=s.request_timeout,
        min_delay_seconds=s.min_delay_seconds,
        bot_accounts=accounts,
        proxies=_parse_proxies(s.proxies),
        search_providers=_split_csv(s.search_providers),
        search_keywords=_split_csv(s.search_keywords),
        search_results_per_keyword=s.search_results_per_keyword,
        search_min_delay=s.search_min_delay,
        search_budget=(s.search_budget or None),
        active_fetch_budget=s.active_fetch_budget,
        searxng_url=s.searxng_url,
    )
