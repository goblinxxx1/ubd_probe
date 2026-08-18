"""Language gate: the crawler takes Ukrainian resources only.

A predominantly non-Cyrillic page (e.g. an English .com blog that slips past the
gTLD geo-gate, since Ukrainian businesses also use .com) carries no Ukrainian
offer and only wastes crawl budget. We judge by the Cyrillic share of the page
text — Ukrainian pages measure ~1.0, English ~0.0, so a low threshold separates
them cleanly. A Latin brand name inside Ukrainian prose (iPhone, Samsung) barely
moves the ratio, so such offers still pass.
"""


def cyrillic_ratio(text: str) -> float:
    """Share of alphabetic characters that are Cyrillic. 0.0 when there are no letters."""
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return 0.0
    cyr = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    return cyr / len(letters)


def is_non_ukrainian(text: str, *, min_ratio: float = 0.3, min_alpha: int = 15) -> bool:
    """True when the text has enough letters to judge AND is predominantly non-Cyrillic.
    Too-short text returns False: we never drop a page merely for lack of content."""
    letters = sum(1 for c in (text or "") if c.isalpha())
    if letters < min_alpha:
        return False
    return cyrillic_ratio(text) < min_ratio
