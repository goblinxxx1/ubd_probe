from crawler.runner import Runner
from crawler.models import RawItem


class _Rec:
    def __init__(self): self.calls = []
    def record(self, item, is_offer, **kw): self.calls.append((item.text, is_offer))


class _Api:
    def list_target_categories(self): return []
    def list_offer_categories(self): return []
    def list_sources(self, is_active=True):
        return [{"id": 1, "type": "website", "name": "Shop", "url_or_handle": "http://x"}]
    def get_crawl_state(self, sid): return {"last_seen_key": None}
    def set_crawl_state(self, sid, key): pass
    def submit_offer(self, p): pass
    def submit_suggestion(self, p): pass
    def expire_stale(self, d): return {"expired": 0}


class _Fetcher:
    def fetch(self, source, key):
        return [RawItem(source_id=1, platform="website", key="k",
                        text="Знижка 20% для ветеранів", url="http://x")], "k"


class _Extractor:
    def extract(self, item, provider, cats):
        return object() if "знижка" in item.text.lower() else None


class _RL:
    def wait(self, *a, **k): pass


def test_runner_records_corpus():
    rec = _Rec()
    Runner(_Api(), {"website": _Fetcher()}, _Extractor(), rate_limiter=_RL(),
           corpus_recorder=rec).run()
    assert ("Знижка 20% для ветеранів", True) in [(t, b) for t, b in rec.calls]
