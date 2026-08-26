"""Персистентний per-URL стор HTTP-валідаторів (ETag/Last-Modified) для conditional
GET. Незмінна сторінка на переобході коштує 304 (кілька байт) замість повного body."""
import json
import os


class ValidatorStore:
    def __init__(self, path: str):
        self._path = path
        try:
            with open(path, encoding="utf-8") as f:
                self._data = json.load(f)
            if not isinstance(self._data, dict):
                self._data = {}
        except (OSError, ValueError):
            self._data = {}

    def get(self, url: str) -> dict | None:
        return self._data.get(url)

    def put(self, url: str, etag: str | None, last_modified: str | None) -> None:
        if not etag and not last_modified:
            return
        self._data[url] = {"etag": etag, "last_modified": last_modified}
        self._save()

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)
