import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from crawler.discovery.blocklist import is_blocked_host, is_blocked_telegram
from crawler.extract.heuristic import _pick_target

_FIRST_PERSON = re.compile(r"\b(ми|у нас|наш\w*|для наших)\b", re.IGNORECASE)


@dataclass
class PageCtx:
    cand_type: str
    cand_name: str
    cand_url_or_handle: str
    brand: str | None
    host: str | None
    offer_block_count: int
    outbound_host_count: int = 0


@dataclass
class Attribution:
    provider: str
    is_first_party: bool
    suggest_type: str | None
    suggest_url_or_handle: str | None
    suggest_name: str | None


def _host(url: str) -> str | None:
    netloc = urlsplit(url or "").netloc.lower().removeprefix("www.")
    return netloc or None


def _origin(url: str) -> str | None:
    p = urlsplit(url or "")
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else None


def _outbound_hosts(passing_items) -> set[str]:
    hosts = set()
    for it in passing_items:
        src_host = _host(getattr(it, "url", None) or "")
        for raw in getattr(it, "links", None) or []:
            h = _host(raw)
            if h and h != src_host and not is_blocked_host(h):
                hosts.add(h)
    return hosts


def build_page_ctx(cand, passing_items) -> PageCtx:
    brand = next((it.site_name for it in passing_items
                  if getattr(it, "site_name", None)), None)
    host = next((_host(it.url) for it in passing_items if it.url), None)
    return PageCtx(
        cand_type=cand.type, cand_name=cand.name, cand_url_or_handle=cand.url_or_handle,
        brand=brand, host=host, offer_block_count=len(passing_items),
        outbound_host_count=len(_outbound_hosts(passing_items)),
    )


def _first_party(ctx: PageCtx) -> Attribution:
    origin = _origin(ctx.cand_url_or_handle) or (f"https://{ctx.host}" if ctx.host else None)
    return Attribution(provider=ctx.brand, is_first_party=True,
                       suggest_type="website", suggest_url_or_handle=origin,
                       suggest_name=ctx.brand)


def attribute(item, ctx: PageCtx, aggregator_min_outbound: int = 3) -> Attribution | None:
    if ctx.cand_type == "telegram":
        if is_blocked_telegram(ctx.cand_url_or_handle, ctx.cand_name):
            return None
        provider = ctx.cand_name or ctx.cand_url_or_handle
        return Attribution(provider=provider, is_first_party=True,
                           suggest_type="telegram",
                           suggest_url_or_handle=ctx.cand_url_or_handle,
                           suggest_name=ctx.cand_name or provider)

    # --- website ---
    is_media = (
        is_blocked_host(ctx.host)
        or (getattr(item, "is_article", False)
            and not getattr(item, "has_business_schema", False))
        or ctx.outbound_host_count >= aggregator_min_outbound
    )
    ext = _pick_target(getattr(item, "links", None), item.url or "")
    clean_ext = ext if (ext and not is_blocked_host(_host(ext))) else None

    if is_media:
        # media/aggregator page is never a provider — salvage via outbound, else drop
        if clean_ext:
            host = _host(clean_ext) or clean_ext
            return Attribution(provider=host, is_first_party=False,
                               suggest_type="website", suggest_url_or_handle=_origin(clean_ext),
                               suggest_name=host)
        return None

    low = (item.text or "").lower()
    # 1. first-party via first-person marker (wins over an outbound link)
    if _FIRST_PERSON.search(low) and ctx.brand:
        return _first_party(ctx)
    # 2. third-party via an external business link
    if clean_ext:
        host = _host(clean_ext) or clean_ext
        return Attribution(provider=host, is_first_party=False,
                           suggest_type="website", suggest_url_or_handle=_origin(clean_ext),
                           suggest_name=host)
    # 3. first-party via a single-business page
    if ctx.offer_block_count <= 1 and ctx.brand:
        return _first_party(ctx)
    # 4. generic info -> no attributable provider
    return None
