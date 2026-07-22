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
    rec = CorpusRecorder(str(p), max_mb=0.0001)  # ~100 bytes
    for i in range(200):
        rec.record(_item(f"Знижка номер {i} " * 3), True)
    size_mb = p.stat().st_size / (1024 * 1024)
    assert size_mb <= 0.0002  # ротація тримає розмір біля межі
    assert len(read_corpus(str(p))) >= 1
