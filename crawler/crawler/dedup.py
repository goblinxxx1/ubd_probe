import hashlib
import re

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s.strip().lower())


def content_hash(title: str, provider: str, body: str) -> str:
    joined = " | ".join(_norm(x) for x in (title, provider, body))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def page_content_hash(title: str, provider: str, discounts: list[dict]) -> str:
    keys = sorted(
        f"{d.get('discount_type')}|{d.get('discount_value')}|{_norm(d.get('label') or '')}"
        for d in discounts
    )
    joined = " | ".join([_norm(title), _norm(provider), *keys])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
