from crawler.models import OfferCandidate
from crawler.payloads import offer_payload


def test_offer_payload_includes_locations():
    cand = OfferCandidate(source_id=1, title="T", provider="P", body="b",
                          locations=["Львів", "Київ"])
    assert offer_payload(cand)["locations"] == ["Львів", "Київ"]


def test_offer_payload_locations_default_empty():
    cand = OfferCandidate(source_id=1, title="T", provider="P", body="b")
    assert offer_payload(cand)["locations"] == []
