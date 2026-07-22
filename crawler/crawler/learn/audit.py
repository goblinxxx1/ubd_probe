"""Черга кандидат-термів + CLI аудиту. approve → LEARNED-дата-файл (єдиний шлях
у живий гейт), reject → стоплист. Промоція завжди через людину."""

import argparse
import json
import os
import time


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def write_candidates(path, survivors) -> None:
    _save(path, [{"term": s.term, "z": round(s.z, 3),
                  "support": len({d for d in s.domains if d})} for s in survivors])


def approve(term, candidates_path, learned_path) -> None:
    learned = _load(learned_path, [])
    if not any(e.get("term") == term for e in learned):
        cand = next((c for c in _load(candidates_path, []) if c.get("term") == term), {})
        learned.append({"term": term, "z": cand.get("z"),
                        "approved_at": int(time.time())})
        _save(learned_path, learned)
    _save(candidates_path, [c for c in _load(candidates_path, []) if c.get("term") != term])


def reject(term, candidates_path, stoplist_path) -> None:
    stop = _load(stoplist_path, [])
    if term not in stop:
        stop.append(term)
        _save(stoplist_path, stop)
    _save(candidates_path, [c for c in _load(candidates_path, []) if c.get("term") != term])


def load_stoplist(path) -> tuple[str, ...]:
    return tuple(_load(path, []))


def _main(argv=None):  # pragma: no cover - CLI wrapper
    p = argparse.ArgumentParser(prog="audit")
    sub = p.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list"); ls.add_argument("--candidates", required=True)
    ap = sub.add_parser("approve"); ap.add_argument("term")
    ap.add_argument("--candidates", required=True); ap.add_argument("--learned", required=True)
    rj = sub.add_parser("reject"); rj.add_argument("term")
    rj.add_argument("--candidates", required=True); rj.add_argument("--stoplist", required=True)
    a = p.parse_args(argv)
    if a.cmd == "list":
        for c in _load(a.candidates, []):
            print(f"{c['term']}\tz={c.get('z')}\tsupport={c.get('support')}")
    elif a.cmd == "approve":
        approve(a.term, a.candidates, a.learned); print(f"approved: {a.term}")
    elif a.cmd == "reject":
        reject(a.term, a.candidates, a.stoplist); print(f"rejected: {a.term}")


if __name__ == "__main__":  # pragma: no cover
    _main()
