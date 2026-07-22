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
