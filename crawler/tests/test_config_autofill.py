from crawler.config import Config


def test_config_has_autofill_defaults():
    c = Config(internal_api_url="x", crawler_api_key="k", extractor="heuristic",
               active_discovery=False, request_timeout=1.0, min_delay_seconds=1.0)
    assert c.promo_lexicon_learned_path.endswith("promo_lexicon_learned.json")
    assert c.miner_min_domain_support == 3
    assert c.autofill_enabled is False
    assert c.corpus_max_mb > 0
