import json

from crawler.discovery.domain_registry import DomainRegistry
from crawler.learn.reject_feedback import RejectionIngestor


class _Api:
    def __init__(self, rows):
        self._rows = rows
        self.since_seen = "UNSET"

    def list_rejected_offers(self, since=None):
        self.since_seen = since
        return self._rows


def _reg():
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}},
                         clock=lambda: 1.0, reject_weight=1.0)
    reg.record("shop.ua", offers=3, errors=0)   # 3.0
    reg.record("news.ua", offers=2, errors=0)   # 2.0
    return reg


def test_ingest_aggregates_per_host_and_downranks(tmp_path):
    reg = _reg()
    api = _Api([
        {"host": "shop.ua", "rejected_at": "2026-08-06T10:00:00"},
        {"host": "shop.ua", "rejected_at": "2026-08-06T11:00:00"},
        {"host": "news.ua", "rejected_at": "2026-08-06T09:00:00"},
    ])
    n = RejectionIngestor(api, reg, str(tmp_path / "since.json")).ingest()
    assert n == 3
    assert reg.score("shop.ua") == 1.0    # 3 - 2*1.0
    assert reg.score("news.ua") == 1.0    # 2 - 1*1.0


def test_ingest_saves_newest_cursor(tmp_path):
    reg = _reg()
    state = str(tmp_path / "since.json")
    api = _Api([
        {"host": "shop.ua", "rejected_at": "2026-08-06T10:00:00"},
        {"host": "news.ua", "rejected_at": "2026-08-06T12:30:00"},
    ])
    RejectionIngestor(api, reg, state).ingest()
    assert json.load(open(state, encoding="utf-8"))["since"] == "2026-08-06T12:30:00"


def test_ingest_passes_saved_since_next_time(tmp_path):
    reg = _reg()
    state = str(tmp_path / "since.json")
    json.dump({"since": "2026-08-01T00:00:00"}, open(state, "w"))
    api = _Api([])
    RejectionIngestor(api, reg, state).ingest()
    assert api.since_seen == "2026-08-01T00:00:00"


def test_ingest_skips_unknown_hosts_but_advances_cursor(tmp_path):
    reg = _reg()
    state = str(tmp_path / "since.json")
    api = _Api([{"host": "ghost.ua", "rejected_at": "2026-08-06T08:00:00"}])
    n = RejectionIngestor(api, reg, state).ingest()
    assert n == 1                                   # row processed
    assert "ghost.ua" not in reg._data["domains"]   # skipped
    assert json.load(open(state, encoding="utf-8"))["since"] == "2026-08-06T08:00:00"


def test_ingest_ignores_empty_host_rows(tmp_path):
    reg = _reg()
    api = _Api([{"host": "", "rejected_at": "2026-08-06T08:00:00"}])
    RejectionIngestor(api, reg, str(tmp_path / "since.json")).ingest()
    assert reg.score("shop.ua") == 3.0   # untouched


def test_ingest_handles_none_rows(tmp_path):
    reg = _reg()
    api = _Api(None)
    assert RejectionIngestor(api, reg, str(tmp_path / "since.json")).ingest() == 0
