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
