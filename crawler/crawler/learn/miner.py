"""Офлайн контраст-майнер: weighted log-odds з informative Dirichlet prior
(Monroe, Colaresi, Quinn 2008) між PASS та FAIL корпусами. Не сира частота."""

import math
from collections import defaultdict
from dataclasses import dataclass, field

from crawler.learn.tokenize import tokenize


@dataclass
class TermScore:
    term: str
    z: float
    pass_count: int
    fail_count: int
    domains: set = field(default_factory=set)
    in_neg_anchor: bool = False
    doc_count: int = 0          # raw (unweighted) count of PASS docs containing the term


def mine(rows, known_stems=(), stoplist=(), snowball_weight: int = 3, alpha: float = 0.5,
         pos_weight: float = 2.0, tokenizer=tokenize):
    y_pass, y_fail = defaultdict(float), defaultdict(float)
    domains = defaultdict(set)
    docs = defaultdict(int)          # raw PASS-doc frequency (unweighted)
    neg = defaultdict(bool)
    for r in rows:
        w = snowball_weight if r.get("snowball") else 1
        if r.get("pos_anchor") and r.get("label") == "pass":
            w *= pos_weight
        toks = set(tokenizer(r.get("text", "")))
        for t in toks:
            if r.get("label") == "pass":
                y_pass[t] += w
                domains[t].add(r.get("host", ""))
                docs[t] += 1
            else:
                y_fail[t] += w
            if r.get("neg_anchor"):
                neg[t] = True

    vocab = set(y_pass) | set(y_fail)
    if len(vocab) < 2:
        return []
    a0 = alpha * len(vocab)
    n_pass = sum(y_pass.values()) + a0
    n_fail = sum(y_fail.values()) + a0

    out = []
    for t in vocab:
        if any(k in t for k in known_stems):
            continue
        if t in stoplist:
            continue
        yp, yf = y_pass[t] + alpha, y_fail[t] + alpha
        delta = math.log(yp / (n_pass - yp)) - math.log(yf / (n_fail - yf))
        var = 1.0 / yp + 1.0 / yf
        z = delta / math.sqrt(var)
        out.append(TermScore(term=t, z=z, pass_count=int(y_pass[t]),
                             fail_count=int(y_fail[t]), domains=domains[t],
                             in_neg_anchor=neg[t], doc_count=docs[t]))
    out.sort(key=lambda s: (-s.z, s.term))
    return out
