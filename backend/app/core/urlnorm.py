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


# Tracking/click-id params stripped in addition to any utm_* prefix.
_TRACKING_PARAMS = frozenset({
    "gclid", "gclsrc", "dclid", "gbraid", "wbraid", "fbclid", "yclid", "msclkid",
    "twclid", "ttclid", "igshid", "mc_eid", "mc_cid", "_openstat", "vero_id",
    "oly_enc_id", "oly_anon_id", "icid", "scid", "srsltid", "spm",
})


def canonicalize_target_url(url: str) -> str | None:
    """Scheme-less, www-less offer dedup key: lowercased host (no port/userinfo, www. dropped),
    path without trailing slash, tracking params (utm_*/click-ids) stripped, rest sorted.
    http↔https collapsed (scheme omitted). Returns None for non-http(s)/junk."""
    if not url:
        return None
    p = urlsplit(url.strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    host = (p.hostname or "").removeprefix("www.")
    if not host:
        return None
    kept = sorted((k, v) for k, v in parse_qsl(p.query)
                  if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS)
    query = urlencode(kept)
    path = p.path.rstrip("/")
    return f"{host}{path}" + (f"?{query}" if query else "")
