from crawler.discovery import blocklist
from crawler.discovery.media_autoblock import MediaAutoBlocker


class FakeApi:
    def __init__(self, boom=False):
        self.calls = []
        self._boom = boom
    def auto_block_host(self, host, sample_url=None):
        self.calls.append((host, sample_url))
        if self._boom:
            raise RuntimeError("network down")
        return {"host": host, "status": "approved"}


def test_block_calls_api_and_runtime_blocklist():
    blocklist.reload_learned(None)
    api = FakeApi()
    MediaAutoBlocker(api).block("dumka.media", "https://dumka.media/x")
    assert api.calls == [("dumka.media", "https://dumka.media/x")]
    assert blocklist.is_blocked_host("dumka.media") is True
    blocklist.reload_learned(None)


def test_block_swallows_api_error_and_skips_runtime_add():
    blocklist.reload_learned(None)
    api = FakeApi(boom=True)
    MediaAutoBlocker(api).block("flaky.example")     # must not raise
    assert blocklist.is_blocked_host("flaky.example") is False
    blocklist.reload_learned(None)


def test_block_ignores_empty_host():
    api = FakeApi()
    MediaAutoBlocker(api).block("")
    assert api.calls == []
