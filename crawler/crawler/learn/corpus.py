"""JSONL-стор корпусу міток PASS/FAIL для офлайн-майнера. Append + ротація за розміром."""

import json
import os
import time
from urllib.parse import urlsplit

from crawler.learn.labeler import label_item


def _outbound_count(item) -> int:
    src = urlsplit(getattr(item, "url", None) or "").netloc.lower().removeprefix("www.")
    hosts = set()
    for raw in getattr(item, "links", None) or []:
        h = urlsplit(raw or "").netloc.lower().removeprefix("www.")
        if h and h != src:
            hosts.add(h)
    return len(hosts)


class CorpusRecorder:
    def __init__(self, path: str, max_mb: float):
        self._path = path
        self._max_bytes = int(max_mb * 1024 * 1024)

    def record(self, item, extracted_is_offer: bool, *, snowball: bool = False) -> None:
        rec = label_item(item, extracted_is_offer)
        row = {
            "text": getattr(item, "text", "") or "",
            "label": rec.label, "host": rec.host,
            "neg_anchor": rec.neg_anchor, "pos_anchor": rec.pos_anchor,
            "is_article": rec.is_article, "outbound_hosts": _outbound_count(item),
            "snowball": snowball, "ts": int(time.time()),
        }
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "a", encoding="utf-8", newline="") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._rotate()

    def _rotate(self) -> None:
        try:
            if os.path.getsize(self._path) <= self._max_bytes:
                return
            with open(self._path, encoding="utf-8", newline="") as fh:
                lines = fh.readlines()
        except OSError:
            return
        # прибрати найстаріші, поки не влізе (лишити хоч 1 рядок)
        while len(lines) > 1 and sum(len(x.encode()) for x in lines) > self._max_bytes:
            lines.pop(0)
        with open(self._path, "w", encoding="utf-8", newline="") as fh:
            fh.writelines(lines)


def read_corpus(path: str) -> list[dict]:
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except OSError:
        return []
    return rows
