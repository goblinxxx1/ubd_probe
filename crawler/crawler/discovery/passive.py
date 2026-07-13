import re

from crawler.models import RawItem, SourceCandidate

_TG = re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})", re.IGNORECASE)
_TG_AT = re.compile(r"(?<![\w/])@([A-Za-z0-9_]{4,})")
_IG = re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]{2,})", re.IGNORECASE)
_FB = re.compile(r"(?:https?://)?(?:www\.)?facebook\.com/([A-Za-z0-9_.]{2,})", re.IGNORECASE)


def normalize_ref(type: str, url_or_handle: str) -> str:
    s = url_or_handle.strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^(www\.)?(t\.me/|instagram\.com/|facebook\.com/)", "", s)
    return s.lstrip("@").rstrip("/")


def _add(cands, seen, known, source_id, type_, handle, note):
    ref = normalize_ref(type_, handle)
    if not ref or ref in known or (type_, ref) in seen:
        return
    seen.add((type_, ref))
    cands.append(SourceCandidate(
        name=handle, type=type_, url_or_handle=handle,
        discovered_from_source_id=source_id, discovery_note=note,
    ))


def extract_source_candidates(item: RawItem, known: set[str]) -> list[SourceCandidate]:
    blob = " ".join([item.text or ""] + [l or "" for l in item.links])
    note = f"Found while crawling source #{item.source_id} ({item.platform})"
    cands: list[SourceCandidate] = []
    seen: set[tuple[str, str]] = set()
    for handle in _TG.findall(blob) + _TG_AT.findall(blob):
        _add(cands, seen, known, item.source_id, "telegram", handle, note)
    for handle in _IG.findall(blob):
        _add(cands, seen, known, item.source_id, "instagram", handle, note)
    for handle in _FB.findall(blob):
        _add(cands, seen, known, item.source_id, "facebook", handle, note)
    return cands
