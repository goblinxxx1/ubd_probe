import logging
import time

log = logging.getLogger(__name__)

MIN_ACTIVE_DELAY = 5.0   # floor so an instantly-returning active pass can't busy-loop


def step(runner, state, passive_schedule, *, active_delay, backoff_max_sleep, hard_factor,
         search_available=None):
    """One scheduling decision: run exactly one pass, return the sleep (seconds).

    - Global backoff active: DDG is unusable, so run the DDG-INDEPENDENT part of the active
      pass (drain + feeds + harvest; no DDG search/site:) plus the passive pass (when its
      cadence is due), then sleep until the backoff lifts (capped).
    - Otherwise: run the DDG active pass (new-offer discovery). Passive runs in
      DDG-available time ONLY as a freshness safety net when it is hard-overdue.

    `search_available()`, when given, decides degraded-vs-full: it reports whether ANY
    search provider (DDG or SearXNG) is currently healthy, so the active pass only
    degrades when every provider is down. Without it, falls back to DDG-only
    state.in_global_backoff() (back-compat)."""
    if search_available is not None:
        backed_off = not search_available()
    else:
        backed_off = state is not None and state.in_global_backoff()
    if state is not None and backed_off:
        runner.run_active(ddg_allowed=False)      # DDG-independent discovery survives backoff
        if passive_schedule is None or passive_schedule.due():
            runner.run_passive()
            if passive_schedule is not None:
                passive_schedule.mark()
        return min(state.seconds_until_allowed(), backoff_max_sleep)
    if passive_schedule is not None and passive_schedule.overdue(hard_factor):
        runner.run_passive()
        passive_schedule.mark()
        return max(active_delay, MIN_ACTIVE_DELAY)
    runner.run_active(ddg_allowed=True)
    return max(active_delay, MIN_ACTIVE_DELAY)


def run_loop(runner, state_loader, passive_schedule, *, active_delay, backoff_max_sleep,
             hard_factor, sleep=time.sleep, iterations=None,
             learn=None, learn_interval_seconds=0, now=time.monotonic,
             search_available=None, refresh=None, refresh_interval_seconds=0):
    """Drive step() forever (or `iterations` times in tests), reloading search state each
    pass so a freshly-persisted next_allowed_at is always seen. A failing pass is logged
    and skipped — it must never kill the loop.

    If `learn` is given and `learn_interval_seconds` > 0, it is invoked on the first
    iteration and then every interval — a self-learning tick that re-mines the query
    lexicon and rebuilds the live grid. It is best-effort: a failure is logged and
    never kills the loop nor blocks the crawl pass."""
    n = 0
    last_learn = None
    last_refresh = None
    while iterations is None or n < iterations:
        if learn is not None and learn_interval_seconds > 0:
            t = now()
            if last_learn is None or (t - last_learn) >= learn_interval_seconds:
                last_learn = t
                try:
                    learn()
                except Exception as exc:  # noqa: BLE001 — learning must not kill the loop
                    log.warning("scheduler learn tick failed: %s", exc)
        if refresh is not None and refresh_interval_seconds > 0:
            t = now()
            if last_refresh is None or (t - last_refresh) >= refresh_interval_seconds:
                last_refresh = t
                try:
                    refresh()
                except Exception as exc:  # noqa: BLE001 — refresh must not kill the loop
                    log.warning("scheduler refresh tick failed: %s", exc)
        try:
            state = state_loader()
            secs = step(runner, state, passive_schedule, active_delay=active_delay,
                        backoff_max_sleep=backoff_max_sleep, hard_factor=hard_factor,
                        search_available=search_available)
        except Exception as exc:  # noqa: BLE001 — a bad pass must not kill the loop
            log.warning("scheduler iteration failed: %s", exc)
            secs = max(active_delay, MIN_ACTIVE_DELAY)
        log.info("scheduler: sleeping %.0fs", secs)
        sleep(secs)
        n += 1
