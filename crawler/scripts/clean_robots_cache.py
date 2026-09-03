"""One-shot: drop robots_cache.json entries whose body exceeds the size cap.
Aligns the on-disk cache with the new _sanitize() guard. Run against /data volume."""
import json, os, sys

MAX = 512 * 1024
path = sys.argv[1] if len(sys.argv) > 1 else "/data/robots_cache.json"
d = json.load(open(path, encoding="utf-8"))
before = len(d)
kept, dropped, freed = {}, [], 0
for k, v in d.items():
    n = len(((v or {}).get("text", "") or "").encode("utf-8", "ignore"))
    if n > MAX:
        dropped.append((n, k)); freed += n
    else:
        kept[k] = v
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(kept, f, ensure_ascii=False)
os.replace(tmp, path)
print(f"entries: {before} -> {len(kept)}  (dropped {len(dropped)})")
print(f"freed ~{freed/1e6:.1f} MB of text; new file {os.path.getsize(path)/1e6:.1f} MB")
for n, k in sorted(dropped, reverse=True)[:10]:
    print(f"  dropped {n/1e6:6.1f} MB  {k}")
