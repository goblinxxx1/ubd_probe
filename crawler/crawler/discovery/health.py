"""Crawler self-health snapshot for the admin monitoring panel.

`build_snapshot` reduces the persistent SearchState into a small, JSON-serialisable
summary the crawler POSTs to the backend. The crawler owns this shape; the backend stores
it opaquely and the admin UI renders it. Pure and side-effect free — trivially testable.
"""
from datetime import datetime, timezone

_DRY_EPSILON = 0.05      # ewma below this = effectively dry (mirrors search_state)
_COLD_TRIES = 3          # a phrase is only "starved" once past the exploration window
_NOISE_TOP = 8


def _backend_status(entry: dict, now: float) -> tuple[str, int, int]:
    """(status, cooldown_s, quarantine_s) for one backend entry, remaining seconds."""
    quarantine_s = max(0, int(entry.get("quarantined_until", 0.0) - now))
    cooldown_s = max(0, int(entry.get("cooldown_until", 0.0) - now))
    if quarantine_s > 0:
        status = "quarantined"
    elif cooldown_s > 0:
        status = "cooling"
    else:
        status = "healthy"
    return status, cooldown_s, quarantine_s


def build_snapshot(state, pool: list[str], now: float) -> dict:
    """Summarise SearchState for monitoring. `pool` is the active backend rotation (so a
    retired backend like mojeek is not shown); backends are reported in pool order."""
    data = state._data
    backends = []
    for name in pool:
        entry = data.get("backends", {}).get(name) or {}
        status, cooldown_s, quarantine_s = _backend_status(entry, now)
        backends.append({
            "name": name, "fails": int(entry.get("fails", 0)),
            "cooldown_s": cooldown_s, "quarantine_s": quarantine_s, "status": status,
        })

    stats = data.get("phrase_stats", {})
    productive = sum(1 for e in stats.values() if float(e.get("ewma", 0.0)) >= _DRY_EPSILON)
    starved = sum(1 for e in stats.values()
                  if float(e.get("ewma", 0.0)) < _DRY_EPSILON
                  and int(e.get("tries", 0)) >= _COLD_TRIES)

    noise = sorted((data.get("host_freq", {}) or {}).items(),
                   key=lambda kv: kv[1], reverse=True)[:_NOISE_TOP]

    return {
        "backends": backends,
        "global_backoff_s": max(0, int(data.get("next_allowed_at", 0.0) - now)),
        "phrases": {"tracked": len(stats), "productive": productive, "starved": starved},
        "recall": {"grid_cursor": int(data.get("grid_cursor", 0)),
                   "cache_entries": len(data.get("cache", {}))},
        "noise_hosts": [{"host": h, "count": int(c)} for h, c in noise],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
