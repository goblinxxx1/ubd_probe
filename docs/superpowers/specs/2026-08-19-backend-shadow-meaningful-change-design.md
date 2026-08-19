# Backend: re-moderation shadow only on a meaningful discount change

**Date:** 2026-08-19
**Status:** Design approved (root fix)

## Problem (recurring)

Re-crawling an already-published offer spawns a re-moderation **shadow** (`create_offer`
branch 2) whenever the new `content_hash` differs from the published parent. But
`content_hash` folds in title/provider/body, so **any extraction noise** — a reworded
label, a provider drift (`Footer-logo`), a spurious `free` footnote, duplicated discount
rows — produces a new hash and therefore a **new shadow in the moderation queue**, even
though the merchant changed nothing.

**Evidence:** published #302 (Smartlab, `percent 30`, "Знижка 30% для захисників Херсона")
kept re-spawning shadow #334 — same core 30% discount, but re-extracted with
`discount_type=free` at top level (a "турбобонус надається за наявності…" footnote won),
three duplicate `percent 30` rows, and `provider=Footer-logo`. The moderator has to reject
it every re-crawl. This is the "we come back to this every time" symptom — the trigger
fires on noise, not on a real change.

## Goal

Spawn a re-moderation shadow only when the published offer's discount **actually changed**
(a value was removed or altered) — not when the re-crawl merely differs in extraction
noise. Preserve genuine change detection (30%→40%, 30%→free-only, discount withdrawn).

## Design

In `create_offer` branch 2 (`backend/app/crud/offer.py`), after locating the published
`parent` and before building the shadow, compare discount **magnitudes** (reusing the
existing `discount_magnitudes` helper, already imported):

```python
        if parent is not None:
            new_mags = discount_magnitudes(getattr(data, "discounts", None),
                                           data.discount_type, data.discount_value)
            parent_mags = discount_magnitudes(parent.discounts, parent.discount_type,
                                              parent.discount_value)
            if parent_mags and parent_mags <= new_mags:
                # The published offer's discount is still fully present in the re-crawl — it
                # differs only in extraction noise (relabeled text, provider drift, extra
                # footnotes/dup rows), not a real merchant change. Do NOT spawn a
                # re-moderation shadow; just bump last_seen and keep the published row.
                parent.last_seen_at = datetime.utcnow()
                db.commit()
                db.refresh(parent)
                return parent
            targets, offers = _load_categories(...)   # existing shadow path continues
            ...
```

**Rule:** `parent_mags ⊆ new_mags` ("everything the published offer promised is still
promised") ⇒ no change ⇒ no shadow. Otherwise ⇒ real change ⇒ shadow (unchanged path).

- #334: parent `{(percent,30)}` ⊆ new `{(percent,30),(free,None)}` ⇒ **no shadow**. Fixed.
- Real change 30%→40%: `{30} ⊄ {40}` ⇒ shadow (kept).
- Withdrawn 30%→free-only: `{30} ⊄ {free}` ⇒ shadow (kept).
- Dropped a tier {30,20}→{30}: `{30,20} ⊄ {30}` ⇒ shadow (kept — a real removal).
- Added a tier 30%→{30,50}: parent `{30}` ⊆ `{30,50}` ⇒ no shadow (an addition is not a
  change to the published offer; accepted — the added tier surfaces on the next real change).

## Blast radius

One guard block in branch 2. No schema/migration, no new helper (reuses
`discount_magnitudes`), no crawler/config change.

## Risks

1. **Extraction misses the discount on a re-crawl** (finds only a footnote) → `parent_mags
   ⊄ new_mags` → a shadow is still spawned. This is an extraction-robustness issue, not a
   regression of this fix; the moderator rejects it as before. Out of scope.
2. A genuinely added discount tier is not surfaced until the next real change. Accepted
   (see rule) — it does not alter the published offer's validity.

## Testing (`backend/tests/`)

- Re-crawl of a published offer with the SAME primary magnitude but noisy extras
  (extra `free`, reworded label, different provider, different content_hash) → returns the
  parent, creates **no** shadow, bumps `last_seen`.
- Re-crawl with a CHANGED magnitude (30→40) → creates a shadow (`supersedes` set).
- Re-crawl that WITHDRAWS the discount (30→free-only) → creates a shadow.
- Re-crawl that DROPS one of two tiers ({30,20}→{30}) → creates a shadow.
- Existing shadow tests still pass (genuine change still shadows).

## Rollout

Rebuild backend. No queue cleanup beyond the already-rejected #334.
