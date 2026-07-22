from crawler.learn.snowball import SnowballIngestor


class _Api:
    def __init__(self, rows): self._rows = rows
    def list_approved_offers(self, since): return self._rows


class _Rec:
    def __init__(self): self.calls = []
    def record(self, item, is_offer, **kw): self.calls.append((item.text, is_offer, kw))


def test_ingest_records_strong_pass(tmp_path):
    api = _Api([{"text": "Знижка для ветеранів", "host": "shop.ua",
                 "approved_at": "2026-07-22T10:00:00"}])
    rec = _Rec()
    n = SnowballIngestor(api, rec, str(tmp_path / "s.json")).ingest()
    assert n == 1
    text, is_offer, kw = rec.calls[0]
    assert is_offer is True and kw.get("snowball") is True


def test_cursor_persisted(tmp_path):
    sp = str(tmp_path / "s.json")
    api = _Api([{"text": "x", "host": "shop.ua", "approved_at": "2026-07-22T10:00:00"}])
    SnowballIngestor(api, _Rec(), sp).ingest()
    import json
    assert json.load(open(sp))["since"] == "2026-07-22T10:00:00"
