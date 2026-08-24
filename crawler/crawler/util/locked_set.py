"""Мінімальна потокобезпечна множина: рівно ті операції, що потрібні пасивному
проходу для спільного `known` (перевірка членства + додавання)."""

import threading


class LockedSet:
    def __init__(self, iterable=None):
        self._set = set(iterable or ())
        self._lock = threading.Lock()

    def add(self, item) -> None:
        with self._lock:
            self._set.add(item)

    def __contains__(self, item) -> bool:
        with self._lock:
            return item in self._set

    def __len__(self) -> int:
        with self._lock:
            return len(self._set)
