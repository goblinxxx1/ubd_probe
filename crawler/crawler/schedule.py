import json
import time


class PassiveSchedule:
    """Persisted cadence gate for the passive pass: due() stays True until the
    interval elapses since the last mark(); state is a tiny JSON file so the
    cadence survives crawler restarts. `now` is injected for tests."""

    def __init__(self, path, interval_seconds, now=time.time):
        self._path = path
        self._interval = interval_seconds
        self._now = now

    def due(self) -> bool:
        last = self._load()
        return last is None or (self._now() - last) >= self._interval

    def mark(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump({"last_passive_at": self._now()}, fh)
        except OSError:
            pass  # best-effort; a missed mark just means passive runs again next loop

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as fh:
                v = json.load(fh).get("last_passive_at")
            return float(v) if v is not None else None
        except (OSError, ValueError):
            return None
