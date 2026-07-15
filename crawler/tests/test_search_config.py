from crawler.config import _split_csv


def test_split_csv_trims_and_drops_empty():
    assert _split_csv("a, b ,,c") == ["a", "b", "c"]
    assert _split_csv("") == []
