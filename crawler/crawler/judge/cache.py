"""Персистентний кеш вердиктів судді по content_hash. Стабілізує повторні
проходи (той самий блок = той самий вердикт) і уникає повторних LLM-викликів."""

import json
import os
import threading

from crawler.judge.base import Verdict


class VerdictCache:
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data = data
        except (OSError, ValueError):
            self._data = {}

    def get(self, content_hash: str) -> Verdict | None:
        with self._lock:
            e = self._data.get(content_hash)
        if not e:
            return None
        return Verdict(genuine=bool(e.get("genuine")),
                       page_scoped=bool(e.get("page_scoped")),
                       reason=str(e.get("reason", "")))

    def put(self, content_hash: str, verdict: Verdict) -> None:
        with self._lock:
            self._data[content_hash] = {"genuine": verdict.genuine,
                                        "page_scoped": verdict.page_scoped,
                                        "reason": verdict.reason}
            directory = os.path.dirname(self._path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp = f"{self._path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False)
            os.replace(tmp, self._path)
