import threading
import time


class RateLimiter:
    def __init__(self, min_delay: float, sleep=time.sleep, monotonic=time.monotonic):
        self._min_delay = min_delay
        self._sleep = sleep
        self._monotonic = monotonic
        self._last: dict[str, float] = {}

    def wait(self, platform: str) -> None:
        now = self._monotonic()
        last = self._last.get(platform)
        if last is not None:
            remaining = self._min_delay - (now - last)
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic() if self._monotonic() > now else now + remaining
        self._last[platform] = now


class DomainRateLimiter:
    """Per-domain лімітер мінімальної затримки. Аргумент `delay` для конкретного виклику
    (напр. robots Crawl-delay) піднімає поріг лише для цього виклику; кожен домен
    відстежується незалежно. Потокобезпечний: короткий guard-лок захищає реєстр
    per-domain локів; кожен домен має ВЛАСНИЙ лок, утримуваний на всьому read-modify-write
    + sleep, тож виклики того самого домену серіалізуються (ввічливість збережена),
    а різні домени виконуються паралельно."""

    def __init__(self, min_delay: float, sleep=time.sleep, monotonic=time.monotonic):
        self._min_delay = min_delay
        self._sleep = sleep
        self._monotonic = monotonic
        self._last: dict[str, float] = {}
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def _domain_lock(self, domain: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(domain)
            if lock is None:
                lock = threading.Lock()
                self._locks[domain] = lock
            return lock

    def wait(self, domain: str, delay: float | None = None) -> None:
        effective = max(self._min_delay, delay or 0.0)
        with self._domain_lock(domain):
            now = self._monotonic()
            last = self._last.get(domain)
            if last is not None:
                remaining = effective - (now - last)
                if remaining > 0:
                    self._sleep(remaining)
                    now = self._monotonic() if self._monotonic() > now else now + remaining
            self._last[domain] = now
