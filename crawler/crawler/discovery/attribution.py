import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from crawler.discovery.blocklist import is_blocked_host
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


def build_page_ctx(cand, passing_items) -> PageCtx:
    brand = next((it.site_name for it in passing_items
                  if getattr(it, "site_name", None)), None)
    host = next((_host(it.url) for it in passing_items if it.url), None)
    return PageCtx(
        cand_type=cand.type, cand_name=cand.name, cand_url_or_handle=cand.url_or_handle,
        brand=brand, host=host, offer_block_count=len(passing_items),
    )


def _first_party(ctx: PageCtx) -> Attribution:
    origin = _origin(ctx.cand_url_or_handle) or (f"https://{ctx.host}" if ctx.host else None)
    return Attribution(provider=ctx.brand, is_first_party=True,
                       suggest_type="website", suggest_url_or_handle=origin,
                       suggest_name=ctx.brand)


def attribute(item, ctx: PageCtx) -> Attribution | None:
    if ctx.cand_type == "telegram":
        provider = ctx.cand_name or ctx.cand_url_or_handle
        return Attribution(provider=provider, is_first_party=True,
                           suggest_type="telegram",
                           suggest_url_or_handle=ctx.cand_url_or_handle,
                           suggest_name=ctx.cand_name or provider)

    # media/gov/stock/social page is never a provider
    if is_blocked_host(ctx.host):
        return None

    low = (item.text or "").lower()
    # 1. first-party via first-person marker (wins over an outbound link)
    if _FIRST_PERSON.search(low) and ctx.brand:
        return _first_party(ctx)
    # 2. third-party via an external business link (skip blocked targets)
    ext = _pick_target(getattr(item, "links", None), item.url or "")
    if ext and not is_blocked_host(_host(ext)):
        host = _host(ext) or ext
        return Attribution(provider=host, is_first_party=False,
                           suggest_type="website", suggest_url_or_handle=_origin(ext),
                           suggest_name=host)
    # 3. first-party via a single-business page (narrowed: essentially one block)
    if ctx.offer_block_count <= 1 and ctx.brand:
        return _first_party(ctx)
    # 4. generic info -> no attributable provider
    return None
