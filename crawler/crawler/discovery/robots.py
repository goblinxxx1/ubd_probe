"""Per-domain robots.txt: fetch (rate-limited, injected client), persist raw text to a JSON
cache with a freshness gate, and parse on read via stdlib urllib.robotparser. Best-effort:
any failure yields an allow-all policy. Mirrors the BrandDomainCache persistence pattern."""

import json
import logging
import os
import time
from urllib.robotparser import RobotFileParser

log = logging.getLogger(__name__)

ROBOTS_UA = "UBDCrawler"


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
        text = self._fetch(domain)
        self._data[domain] = {"fetched_at": self._clock(), "text": text}
        try:
            self._save()
        except OSError as exc:  # noqa: BLE001 — cache write is best-effort
            log.warning("robots cache save failed: %s", exc)
        return ParsedRobots(text)

    def _fetch(self, domain: str) -> str:
        url = f"https://{domain}/robots.txt"
        try:
            self._rl.wait(domain)
            resp = self._client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.text or ""
        except Exception as exc:  # noqa: BLE001 — allow-all on any failure
            log.warning("robots fetch failed for %s: %s", domain, exc)
            return ""
