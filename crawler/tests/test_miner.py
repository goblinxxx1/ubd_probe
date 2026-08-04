from crawler.learn.miner import mine


def _row(text, label, host, neg=False, pos=False):
    return {"text": text, "label": label, "host": host, "neg_anchor": neg,
            "snowball": False, "pos_anchor": pos}


def test_pass_associated_term_scores_positive():
    rows = ([_row("уцінка на все", "pass", f"d{i}.ua") for i in range(5)]
            + [_row("звичайна новина міста", "fail", f"n{i}.ua") for i in range(5)])
    scores = mine(rows, known_stems=())
    top = {s.term for s in scores if s.z > 1.5}
    assert "уцінка" in top


def test_known_stem_excluded():
    rows = ([_row("знижка знижка", "pass", "a.ua")]
            + [_row("новина", "fail", "b.ua")])
    scores = mine(rows, known_stems=("знижк",))
    assert all("знижк" not in s.term for s in scores)


def test_pos_anchor_raises_z():
    base_rows = ([_row("акція для ветеранів", "pass", f"d{i}.ua") for i in range(5)]
                 + [_row("звичайна новина міста", "fail", f"n{i}.ua") for i in range(5)])
    anchored_rows = ([_row("акція для ветеранів", "pass", f"d{i}.ua", pos=True)
                      for i in range(5)]
                     + [_row("звичайна новина міста", "fail", f"n{i}.ua") for i in range(5)])

    z_no_anchor = {s.term: s.z for s in mine(base_rows, known_stems=())}["акція"]
    z_with_anchor = {s.term: s.z for s in mine(anchored_rows, known_stems=())}["акція"]

    assert z_with_anchor > z_no_anchor


def test_mine_default_tokenizer_is_unchanged():
    rows = [{"text": "знижка знижка", "label": "pass", "host": "a.com", "snowball": True},
            {"text": "новини", "label": "fail", "host": "b.com"}]
    # default tokenizer path still produces scores (byte-eq promo behavior)
    scores = mine(rows)
    assert any(s.term == "знижка" for s in scores)


def test_mine_single_token_vocab_returns_empty_no_zerodivision():
    rows = [{"text": "стоматологія", "label": "pass", "host": "a.com"}]
    scores = mine(rows)
    assert scores == []


def test_mine_accepts_custom_tokenizer():
    # NOTE: a single-term vocab makes mine()'s log-odds denominator
    # (alpha*(len(vocab)-1)) exactly 0 -> ZeroDivisionError, a pre-existing
    # edge case unrelated to the tokenizer param. Use >=2 distinct terms so
    # the formula is well-defined, while still proving the custom tokenizer
    # (not the default `tokenize`) drives which terms get mined: "акція" is
    # in the raw text but only appears via default tokenize, not our lambda.
    rows = [{"text": "стоматологія акція", "label": "pass", "host": "a.com"},
            {"text": "новини", "label": "fail", "host": "b.com"}]
    scores = mine(rows, tokenizer=lambda t: ["стоматологія", "клініка"]
                  if "стоматологія" in t else (["новини"] if t else []))
    assert "стоматологія" in [s.term for s in scores]
    assert "акція" not in [s.term for s in scores]
