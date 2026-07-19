"""Resolve lexicon (name, slug) offer matches to DB category ids, creating any
missing offer category once per run. cats.offer doubles as the in-run cache."""


def resolve_offer_categories(api, cats, matches) -> list[int]:
    if not matches:
        return []
    by_slug = {c["slug"]: c for c in cats.offer}
    ids = []
    for name, slug in matches:
        row = by_slug.get(slug)
        if row is None:
            row = api.create_offer_category(name, slug)
            cats.offer.append(row)
            by_slug[slug] = row
        ids.append(row["id"])
    return ids
