"""Per-domain robots.txt: fetch (rate-limited, injected client), persist raw text to a JSON
cache with a freshness gate, and parse on read via stdlib urllib.robotparser. Best-effort:
any failure yields an allow-all policy. Mirrors the BrandDomainCache persistence pattern."""

import json
import logging
import os
import threading
import time
from urllib.robotparser import RobotFileParser

log = logging.getLogger(__name__)

ROBOTS_UA = "UBDCrawler"

# Legitimate robots.txt are tiny (bytes to tens of KB). A larger body means the server
# returned a soft-200 blob instead — an HTML page, an SPA shell, even a binary installer
# — which must NOT be cached verbatim (a single 144MB .exe once ballooned the cache to
# 391MB, re-serialized on every fetch). Anything over the cap, or not served as text/*,
# is discarded → allow-all, the same safe default as a failed fetch.
_MAX_ROBOTS_BYTES = 512 * 1024


def _sanitize(resp) -> str:
    """Keep the body only if it is a plausible robots.txt: served as text/* (or with no
    content-type) AND within the size cap. Otherwise return "" (allow-all). Guards the
    cache against soft-200 HTML pages and binary payloads served at /robots.txt."""
    headers = getattr(resp, "headers", None) or {}
    ctype = (headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if ctype and not ctype.startswith("text/"):
        return ""
    clen = headers.get("content-length")
    if clen and str(clen).isdigit() and int(clen) > _MAX_ROBOTS_BYTES:
        return ""
    text = resp.text or ""
    if len(text.encode("utf-8", "ignore")) > _MAX_ROBOTS_BYTES:
        return ""
    return text


class ParsedRobots:
    """Thin wrapper over a parsed RobotFileParser. An empty/failed parse allows everything."""

    def __init__(self, text: str):
        self._rp = RobotFileParser()
        self._rp.parse((text or "").splitlines())

    def can_fetch(self, url: str) -> bool:
        try:
            return self._rp.can_fetch(ROBOTS_UA, url)
        except Exception:  # noqa: BLE001 — never block on a parser edge case
            return True

    def crawl_delay(self) -> float | None:
        try:
            d = self._rp.crawl_delay(ROBOTS_UA)
            return float(d) if d is not None else None
        except Exception:  # noqa: BLE001
            return None

    def sitemaps(self) -> list[str]:
        try:
            return list(self._rp.site_maps() or [])
        except Exception:  # noqa: BLE001
            return []


class RobotsPolicy:
    def __init__(self, client, rate_limiter, path: str, ttl_seconds: float,
                 clock=time.time):
        self._client = client
        self._rl = rate_limiter
        self._path = path
        self._ttl = ttl_seconds
        self._clock = clock
        self._data = self._load()
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)

    def _fresh(self, entry: dict) -> bool:
        return self._clock() - float(entry.get("fetched_at", 0.0)) < self._ttl

    def get(self, domain: str) -> ParsedRobots:
        entry = self._data.get(domain)
        if isinstance(entry, dict) and self._fresh(entry):
            return ParsedRobots(entry.get("text", ""))
        text = self._fetch(domain)          # мережа — поза локом (має власний per-domain rl.wait)
        with self._lock:
            self._data[domain] = {"fetched_at": self._clock(), "text": text}
            try:
                self._save()
            except OSError as exc:  # noqa: BLE001 — запис кешу best-effort
                log.warning("robots cache save failed: %s", exc)
        return ParsedRobots(text)

    def _fetch(self, domain: str) -> str:
        url = f"https://{domain}/robots.txt"
        try:
            self._rl.wait(domain)
            resp = self._client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return _sanitize(resp)
        except Exception as exc:  # noqa: BLE001 — allow-all on any failure
            log.warning("robots fetch failed for %s: %s", domain, exc)
            return ""
