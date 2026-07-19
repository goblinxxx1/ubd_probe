from crawler.models import OfferCandidate
from crawler.payloads import offer_payload


def test_offer_payload_includes_location():
    cand = OfferCandidate(source_id=None, title="T", provider="P", body="B",
                          location="Львів")
    assert offer_payload(cand)["location"] == "Львів"


def test_offer_payload_location_defaults_none():
    cand = OfferCandidate(source_id=None, title="T", provider="P", body="B")
    assert offer_payload(cand)["location"] is None
