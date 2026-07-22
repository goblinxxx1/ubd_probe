from crawler.learn.miner import mine


def _row(text, label, host, neg=False):
    return {"text": text, "label": label, "host": host, "neg_anchor": neg, "snowball": False}


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
