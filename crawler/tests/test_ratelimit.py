from crawler.ratelimit import RateLimiter


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
