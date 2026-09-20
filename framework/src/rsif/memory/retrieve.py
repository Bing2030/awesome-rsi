"""Hand-rolled lexical retrieval (TF-IDF), no numpy/scikit dependency.

Behind a `Retriever` Protocol so an embeddings-backed retriever can slot in
later as an optional extra.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Protocol


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _stem(token: str) -> str:
    """Minimal, safe suffix stemmer so 'sort'/'sorted'/'sorting' unify.

    Not full Porter stemming - just the gerund/past/plural suffixes that
    dominate this domain's vocabulary. Long enough words only, to avoid
    mangling short words.
    """
    if len(token) > 4 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN_RE.findall(text.lower())]


class Retriever(Protocol):
    def retrieve(self, query: str, documents: list[str], top_k: int = 5) -> list[tuple[int, float]]:
        """Return [(doc_index, score)] sorted descending, at most top_k."""


class TfidfRetriever:
    def retrieve(self, query: str, documents: list[str], top_k: int = 5) -> list[tuple[int, float]]:
        if not documents:
            return []
        doc_tokens = [tokenize(d) for d in documents]
        doc_tf = [Counter(t) for t in doc_tokens]
        doc_len = [len(t) or 1 for t in doc_tokens]
        n = len(documents)

        df: Counter = Counter()
        for tokens in doc_tokens:
            df.update(set(tokens))

        query_tokens = tokenize(query)
        scored: list[tuple[int, float]] = []
        for i, tf in enumerate(doc_tf):
            score = 0.0
            for term in set(query_tokens):
                if term not in tf:
                    continue
                idf = math.log((1 + n) / (1 + df[term])) + 1.0
                score += (tf[term] / doc_len[i]) * idf
            if score > 0.0:
                scored.append((i, score))
        scored.sort(key=lambda p: p[1], reverse=True)
        return scored[:top_k]
