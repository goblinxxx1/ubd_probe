import logging
import time

log = logging.getLogger(__name__)

MIN_ACTIVE_DELAY = 5.0   # floor so an instantly-returning active pass can't busy-loop


def step(runner, state, passive_schedule, *, active_delay, backoff_max_sleep, hard_factor):
    """One scheduling decision: run exactly one pass, return the sleep (seconds).

    - Global backoff active: DDG is unusable, so run the DDG-independent passive pass
      (only if its cadence is due) and sleep until the backoff lifts (capped).
    - Otherwise: run the DDG active pass (new-offer discovery). Passive runs in
      DDG-available time ONLY as a freshness safety net when it is hard-overdue.
    """
    if state is not None and state.in_global_backoff():
        if passive_schedule is None or passive_schedule.due():
            runner.run_passive()
            if passive_schedule is not None:
                passive_schedule.mark()
        return min(state.seconds_until_allowed(), backoff_max_sleep)
    if passive_schedule is not None and passive_schedule.overdue(hard_factor):
        runner.run_passive()
        passive_schedule.mark()
        return max(active_delay, MIN_ACTIVE_DELAY)
    runner.run_active()
    return max(active_delay, MIN_ACTIVE_DELAY)


def run_loop(runner, state_loader, passive_schedule, *, active_delay, backoff_max_sleep,
             hard_factor, sleep=time.sleep, iterations=None):
    """Drive step() forever (or `iterations` times in tests), reloading search state each
    pass so a freshly-persisted next_allowed_at is always seen. A failing pass is logged
    and skipped — it must never kill the loop."""
    n = 0
    while iterations is None or n < iterations:
        try:
            state = state_loader()
            secs = step(runner, state, passive_schedule, active_delay=active_delay,
                        backoff_max_sleep=backoff_max_sleep, hard_factor=hard_factor)
        except Exception as exc:  # noqa: BLE001 — a bad pass must not kill the loop
            log.warning("scheduler iteration failed: %s", exc)
            secs = max(active_delay, MIN_ACTIVE_DELAY)
        log.info("scheduler: sleeping %.0fs", secs)
        sleep(secs)
        n += 1
