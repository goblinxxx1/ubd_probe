import json
import threading

from crawler.discovery.validator_store import ValidatorStore


def test_put_get_roundtrip(tmp_path):
    s = ValidatorStore(str(tmp_path / "v.json"))
    s.put("https://a.ua", etag='"abc"', last_modified="Wed, 21 Oct 2026 07:28:00 GMT")
    assert s.get("https://a.ua") == {"etag": '"abc"',
                                     "last_modified": "Wed, 21 Oct 2026 07:28:00 GMT"}
    assert s.get("https://missing.ua") is None


def test_put_is_thread_safe_no_corruption(tmp_path):
    # Регресія: два ThreadPool'и (active_workers=4, passive_workers=4) б'ють
    # у СПІЛЬНИЙ ValidatorStore одночасно. Без лока put() ловить
    # "dict changed size during iteration" всередині _save(), і виняток
    # тихо ковтається WebFetcher.fetch -> валідний офер губиться мовчки.
    path = str(tmp_path / "validators.json")
    s = ValidatorStore(path)
    n = 200
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def worker(i):
        try:
            s.put(f"https://h{i}.ua", etag=f'"e{i}"', last_modified=f"m{i}")
        except BaseException as e:  # без лока put() падає з "dict changed
            with errors_lock:       # size during iteration" / PermissionError
                errors.append(e)    # на конкурентному os.replace

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"конкурентні put() впали: {errors!r}"

    # файл валідний JSON і всі ключі збереглися
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == n

    # перечитується наново
    s2 = ValidatorStore(path)
    for i in range(n):
        assert s2.get(f"https://h{i}.ua") == {"etag": f'"e{i}"', "last_modified": f"m{i}"}
