import hashlib
import re

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s.strip().lower())


def content_hash(title: str, provider: str, body: str) -> str:
    joined = " | ".join(_norm(x) for x in (title, provider, body))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
