from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_source_ref(url: str) -> str | None:
    """Canonical http(s) ref for source dedup: lowercased host, no trailing slash,
    no fragment, utm_* query params stripped. Returns None for non-http(s)/junk."""
    if not url:
        return None
    p = urlsplit(url.strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(p.query)
                       if not k.lower().startswith("utm_")])
    path = p.path.rstrip("/")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))
