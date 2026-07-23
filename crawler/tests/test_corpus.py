import json

from crawler.learn.corpus import CorpusRecorder, read_corpus
from crawler.models import RawItem


def _item(text, url="https://shop.ua/sale"):
    return RawItem(source_id=1, platform="website", key="k", text=text, url=url)


def test_record_appends_jsonl(tmp_path):
    p = tmp_path / "corpus.jsonl"
    rec = CorpusRecorder(str(p), max_mb=10)
    rec.record(_item("Знижка 20%"), True)
    rec.record(_item("Просто новина", url="https://nv.ua/x"), False)
    rows = read_corpus(str(p))
    assert len(rows) == 2
    assert rows[0]["label"] == "pass" and rows[0]["host"] == "shop.ua"
    assert rows[1]["label"] == "fail"


def test_rotation_trims_oldest(tmp_path):
    p = tmp_path / "corpus.jsonl"
    rec = CorpusRecorder(str(p), max_mb=0.0001)  # ~100 bytes → keeps only newest row(s)
    for i in range(200):
        rec.record(_item(f"Знижка номер {i} " * 3), True)
    rows = read_corpus(str(p))
    # ротація відрізала старі рядки, але ніколи не спорожнила файл (лишає ≥1 рядок,
    # навіть якщо один рядок сам по собі > max_bytes). Поведінковий бавунд, не крихкий байт-точний.
    assert 1 <= len(rows) < 200
    assert p.stat().st_size <= 1024  # далеко під розміром 200 нерозротованих рядків


def test_corpus_row_has_article_and_outbound(tmp_path):
    p = str(tmp_path / "c.jsonl")
    it = RawItem(source_id=None, platform="website", key="k", text="Знижка 20%",
                 url="https://blog.example/a", links=["https://shop.ua/x", "https://blog.example/y"],
                 is_article=True)
    CorpusRecorder(p, max_mb=50).record(it, extracted_is_offer=True)
    rows = read_corpus(p)
    assert rows[0]["is_article"] is True
    assert rows[0]["outbound_hosts"] == 1        # shop.ua external; blog.example internal
