"""Soft, non-permanent query stoplist: records {term, z_at_reject}. A rejected term
stays suppressed only while its new z ≤ z_at_reject × resurface_factor — so a service
that gains much stronger support later can resurface. Categories override (unstop)."""

import argparse
import json
import os


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default
    if not isinstance(data, type(default)):
        return default
    return data


def _save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load_blocked(path) -> dict[str, float]:
    return {e["term"]: float(e.get("z") or 0.0)
            for e in _load(path, []) if isinstance(e, dict) and e.get("term")}


def reject(term, candidates_path, stoplist_path) -> None:
    cand = next((c for c in _load(candidates_path, [])
                 if isinstance(c, dict) and c.get("term") == term), {})
    stop = _load(stoplist_path, [])
    if not any(isinstance(e, dict) and e.get("term") == term for e in stop):
        stop.append({"term": term, "z": float(cand.get("z") or 0.0)})
        _save(stoplist_path, stop)
    _save(candidates_path, [c for c in _load(candidates_path, [])
                             if not (isinstance(c, dict) and c.get("term") == term)])


def unstop(term, stoplist_path) -> None:
    stop = _load(stoplist_path, [])
    kept = [e for e in stop if not (isinstance(e, dict) and e.get("term") == term)]
    if len(kept) != len(stop):
        _save(stoplist_path, kept)


def is_suppressed(term, z, blocked, factor) -> bool:
    if term not in blocked:
        return False
    return z <= blocked[term] * factor


def _main(argv=None):
    p = argparse.ArgumentParser(prog="query_stoplist")
    sub = p.add_subparsers(dest="cmd", required=True)
    rj = sub.add_parser("reject")
    rj.add_argument("term")
    rj.add_argument("--candidates", required=True)
    rj.add_argument("--stoplist", required=True)
    us = sub.add_parser("unstop")
    us.add_argument("term")
    us.add_argument("--stoplist", required=True)
    a = p.parse_args(argv)
    if a.cmd == "reject":
        reject(a.term, a.candidates, a.stoplist)
        print(f"rejected: {a.term}")
    elif a.cmd == "unstop":
        unstop(a.term, a.stoplist)
        print(f"unstopped: {a.term}")


if __name__ == "__main__":  # pragma: no cover
    _main()
