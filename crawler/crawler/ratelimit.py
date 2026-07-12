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
