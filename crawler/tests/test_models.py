from crawler.models import SourceCandidate


def test_source_candidate_origin_key_optional_default_none():
    c = SourceCandidate(name="Shop", type="website", url_or_handle="https://x.ua")
    assert c.origin_key is None


def test_source_candidate_origin_key_settable():
    c = SourceCandidate(name="Shop", type="website", url_or_handle="https://x.ua",
                        origin_key="стоматологія знижка убд")
    assert c.origin_key == "стоматологія знижка убд"
