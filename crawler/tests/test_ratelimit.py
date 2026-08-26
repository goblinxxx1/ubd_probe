import threading

from crawler.ratelimit import RateLimiter, DomainRateLimiter


def test_first_call_no_wait_then_throttles():
    slept = []
    clock = {"t": 100.0}
    rl = RateLimiter(min_delay=2.0, sleep=lambda s: slept.append(s),
                     monotonic=lambda: clock["t"])

    rl.wait("instagram")          # first call: nothing to wait for
    assert slept == []

    clock["t"] = 100.5            # 0.5s elapsed, need 2.0
    rl.wait("instagram")
    assert slept and abs(slept[-1] - 1.5) < 1e-6

    # a different platform has its own independent clock
    rl.wait("telegram")
    assert len(slept) == 1


def _fake_clock():
    t = {"now": 0.0}
    return t


def test_domain_rate_limiter_waits_min_delay_per_domain():
    slept = []
    t = {"now": 100.0}
    rl = DomainRateLimiter(min_delay=5.0, sleep=lambda s: slept.append(s),
                           monotonic=lambda: t["now"])
    rl.wait("a.ua")            # first call for domain -> no wait
    rl.wait("a.ua")            # immediate second call -> waits full min_delay
    assert slept == [5.0]


def test_domain_rate_limiter_isolates_domains():
    slept = []
    t = {"now": 0.0}
    rl = DomainRateLimiter(min_delay=5.0, sleep=lambda s: slept.append(s),
                           monotonic=lambda: t["now"])
    rl.wait("a.ua")
    rl.wait("b.ua")            # different domain -> no wait
    assert slept == []


def test_domain_rate_limiter_per_call_delay_overrides_min():
    slept = []
    t = {"now": 0.0}
    rl = DomainRateLimiter(min_delay=2.0, sleep=lambda s: slept.append(s),
                           monotonic=lambda: t["now"])
    rl.wait("a.ua")
    rl.wait("a.ua", delay=9.0)  # crawl-delay bigger than floor -> waits 9.0
    assert slept == [9.0]


def test_domain_rate_limiter_lock_is_per_domain_not_global():
    """While a slow sleep for domain A is in progress, a wait() for domain B must
    NOT block — proves the lock is per-domain, not a single global lock held during
    sleep (which would serialize all domains and kill parallelism)."""
    a_sleeping = threading.Event()
    release_a = threading.Event()

    def sleep(_s):
        # Only the second (throttled) call for "a.ua" actually sleeps.
        a_sleeping.set()
        release_a.wait(timeout=5)

    t = {"now": 0.0}
    rl = DomainRateLimiter(min_delay=5.0, sleep=sleep, monotonic=lambda: t["now"])

    rl.wait("a.ua")  # primes a.ua; no sleep yet
    a_done = threading.Event()

    def slow_a():
        rl.wait("a.ua")   # immediate re-call -> throttles -> enters sleep()
        a_done.set()

    threading.Thread(target=slow_a, daemon=True).start()
    assert a_sleeping.wait(timeout=5)      # a.ua is now parked inside sleep()

    b_done = threading.Event()

    def call_b():
        rl.wait("b.ua")   # different domain -> must proceed without waiting on a.ua
        b_done.set()

    threading.Thread(target=call_b, daemon=True).start()
    assert b_done.wait(timeout=5), "b.ua blocked on a.ua's lock -> lock is global, not per-domain"

    release_a.set()
    assert a_done.wait(timeout=5)


class _Clock:
    def __init__(self): self.t = 0.0; self.slept = []
    def monotonic(self): return self.t
    def sleep(self, s):
        self.slept.append(s); self.t += s


def test_penalize_forces_wait_until_retry_after():
    c = _Clock()
    rl = DomainRateLimiter(min_delay=0.0, sleep=c.sleep, monotonic=c.monotonic)
    rl.wait("shop.ua")                 # first call, no wait
    rl.penalize("shop.ua", 30.0)       # server said Retry-After: 30
    rl.wait("shop.ua")                 # must sleep ~30s
    assert c.slept and abs(sum(c.slept) - 30.0) < 1e-6


def test_penalize_ignores_nonpositive():
    c = _Clock()
    rl = DomainRateLimiter(min_delay=0.0, sleep=c.sleep, monotonic=c.monotonic)
    rl.penalize("x.ua", 0.0)
    rl.wait("x.ua")
    assert c.slept == []
