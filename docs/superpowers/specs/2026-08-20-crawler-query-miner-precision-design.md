# Crawler: query-miner precision (axis-veto + threshold) — Track A2

**Date:** 2026-08-20
**Status:** Design approved
**Program:** close the self-learning loop (A2 miner precision → A1 admin audit surface).
See [[ubd-crawler-query-miner-audience-bug]].

## Problem

The query miner surfaces AUDIENCE/generic words instead of SERVICE nouns, so the audit
queue is garbage and 0 terms get learned → the grid never self-grows.

**Evidence (verify-by-execution):** learned lexicon = 23 category-bootstrap entries,
**0 miner-learned**. The 7 audit candidates are all noise: `знижка`(z=2.34), `дія`,
`учасник`, `військовослужбовець`, `ветеран`, `україна` — audiences/intent/geo, NOT
services. Root causes:
1. **No axis-veto:** `tokenize.service_terms` keeps any NOUN; audience words (ветеран,
   учасник) are nouns → candidates, and log-odds ranks them high (distinctive to our
   offers). No cross-check against the grid axes (audience/intent) or geo/doc words.
2. **`min_logodds=1.5` too high** for the small corpus (768 rows): real services score
   z≈1.0 (імплантація 1.05, проживання 1.04) — below the threshold; audiences >1.5.

**Proven fixable:** with a 62-word axis-veto (lemmas of AUDIENCE_FORMS+INTENT_FORMS+doc/geo)
the real services surface — `імплантація, зуби, проживання, відпочинок, лікування,
седації, видалення, стоматологія, квиток`. The corpus HAS them; audiences crowded them out.

Documented in the ATE literature: "traditional corpus methods can't auto-exclude
meaningless words" — the axis-veto is the standard remedy; the human audit gate stays as
the drift guardrail (precision > recall).

## Goal

Make the miner surface genuine SERVICE/category terms into the audit queue by (a) vetoing
grid-axis words (audience/intent), geo, and generic/eligibility words, and (b) lowering
the log-odds floor so real services survive. Keep the human audit gate unchanged.

Non-goal: the admin audit UI (that is Track A1). Non-goal: contrastive-with-general-corpus
re-scoring (a later A2.v2 enhancement). This track is crawler-only, isolated behind the
audit gate — it cannot alter the live grid.

## Design

### New helper — `crawler/crawler/learn/axis_veto.py`

```python
"""Terms that are grid AXES or generic noise — never a SERVICE, so the query miner must
not surface them as candidates. Lemmatized to match the miner's service_terms lemmas."""

from crawler.discovery.query_grid import AUDIENCE_FORMS, INTENT_FORMS, GRID_CITIES
from crawler.learn.tokenize import _lemma

# Generic / eligibility / geo nouns that recur in offers but are not services.
_NON_SERVICE = (
    "послуга", "вартість", "ціна", "пакет", "програма", "умова", "наявність",
    "участь", "право", "сила", "посвідчення", "документ", "знак", "повага",
    "вдячність", "захід", "служба", "центр", "година",
    "україна", "дія", "місто", "область", "країна", "територія", "київ",
)


def _lemmas_of(phrases) -> set[str]:
    out: set[str] = set()
    for phrase in phrases:
        for w in phrase.replace("'", "'").lower().split():
            lem = _lemma(w)
            if len(lem) >= 3:
                out.add(lem)
    return out


def axis_veto_terms() -> frozenset[str]:
    veto = _lemmas_of(AUDIENCE_FORMS) | _lemmas_of(INTENT_FORMS) | _lemmas_of(GRID_CITIES)
    veto |= {_lemma(w) for w in _NON_SERVICE}
    return frozenset(v for v in veto if v)


def is_axis_or_noise(term: str, veto: frozenset[str]) -> bool:
    """True if the whole term is vetoed, or (for a bigram) every word is vetoed."""
    if term in veto:
        return True
    words = term.split()
    return len(words) > 1 and all(w in veto for w in words)
```

### Apply in `run_query_miner` (`crawler/crawler/learn/run_query_miner.py`)

After `mine(...)` and before `survivors(...)`, drop axis/noise terms:

```python
    from crawler.learn.axis_veto import axis_veto_terms, is_axis_or_noise
    veto = axis_veto_terms()
    scores = [s for s in scores if not is_axis_or_noise(s.term, veto)]
    # ... existing is_suppressed filter + survivors(...)
```

### Threshold — lower the log-odds floor

`query_miner_min_logodds: 1.5 → 0.9` (config, both `_RawSettings` and `Config` + mapping).
Real services score z≈1.0; 0.9 admits them while `min_domain_support=3` and the axis-veto
keep precision. The human audit gate is the final filter. (`min_domain_support` unchanged.)

## Blast radius

- New module `axis_veto.py`; one filter line in `run_query_miner`; one config default.
- **Isolated behind the audit gate:** the miner writes to the candidate queue (file/Track-A1
  backend), never to the live grid. A wrong veto = a different candidate list, never a
  broken grid. No wiring, no live-path change.

## Risks

1. **Over-veto** (a real service lemma collides with an axis/noise word) → it silently
   never surfaces. Mitigated: the veto is grid-axis + a small curated list; a colliding
   service is rare, and the moderator can still add it manually. Low.
2. **Lower floor admits more noise** → the audit queue grows. Mitigated by the veto + the
   `min_domain_support=3` gate; the human audit filters the rest. Low (a few extra clicks).

## Testing (`crawler/tests/test_axis_veto.py`, `test_run_query_miner.py`)

- `axis_veto_terms()` contains the lemmas of `ветеран`, `знижка`, `київ`; does NOT contain
  `імплантація`, `стоматологія`, `окуляри`.
- `is_axis_or_noise("учасник дія", veto)` → True (both vetoed); `("протезування зубів", veto)`
  → False.
- `run_query_miner` on a fixture corpus (offers mixing "знижка для ветеранів на
  імплантацію" across ≥3 domains) writes candidates that include `імплантація` and exclude
  `ветеран`/`знижка`.
- Config: `query_miner_min_logodds` default is 0.9.

## Rollout

Rebuild crawler. The next 24h learn tick (or a manual `run_query_miner`) re-mines with the
veto → the audit queue fills with real services — ready for Track A1's admin approval UI.
