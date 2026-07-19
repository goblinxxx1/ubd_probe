def offer_payload(cand) -> dict:
    return {
        "type": cand.offer_type,
        "title": cand.title,
        "description": cand.body,
        "provider": cand.provider,
        "location": cand.location,
        "discount_type": cand.discount_type,
        "discount_value": cand.discount_value,
        "valid_from": cand.valid_from.isoformat() if cand.valid_from else None,
        "valid_until": cand.valid_until.isoformat() if cand.valid_until else None,
        "source_id": cand.source_id,
        "content_hash": cand.content_hash,
        "site_url": cand.site_url,
        "article_url": cand.article_url,
        "image_url": cand.image_url,
        "target_url": cand.target_url,
        "target_category_ids": cand.target_category_ids,
        "offer_category_ids": cand.offer_category_ids,
    }


def suggestion_payload(sc) -> dict:
    return {
        "name": sc.name,
        "type": sc.type,
        "url_or_handle": sc.url_or_handle,
        "discovered_from_source_id": sc.discovered_from_source_id,
        "discovery_note": sc.discovery_note,
    }
