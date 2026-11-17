"""Own Okapi BM25 implementation with an inverted index."""

import math
from collections import Counter
from collections.abc import Callable, Sequence

from .text import tokenize

K1 = 1.2
B = 0.75

Tokenizer = Callable[[str], list[str]]


class BM25Index:
    """Inverted BM25 index over a fixed list of texts.

    Attributes:
        postings: Mapping ``term → {text index: term frequency}``.
        lengths: Token count of each indexed text.
        avgdl: Average token count over all texts, 0 for an empty index.
        k1: Term frequency saturation parameter.
        b: Length normalization parameter.
    """

    def __init__(
        self,
        texts: Sequence[str],
        tokenizer: Tokenizer = tokenize,
        k1: float = K1,
        b: float = B,
    ) -> None:
        """Tokenize texts and build the inverted index.

        Args:
            texts: Texts to index; their positions are the text indices.
            tokenizer: Function that turns text into tokens.
            k1: Term frequency saturation parameter.
            b: Length normalization parameter.
        """
        self.tokenizer = tokenizer
        self.k1 = k1
        self.b = b
        self.postings: dict[str, dict[int, int]] = {}
        self.lengths: list[int] = []
        for index, text in enumerate(texts):
            tokens = tokenizer(text)
            self.lengths.append(len(tokens))
            for term, tf in Counter(tokens).items():
                self.postings.setdefault(term, {})[index] = tf
        self.avgdl = sum(self.lengths) / len(self.lengths) if self.lengths else 0

    def idf(self, term: str) -> float:
        """Return ``ln(1 + (N − df + 0.5) / (df + 0.5))`` for a term.

        Args:
            term: Token produced by the index tokenizer.

        Returns:
            Positive inverse document frequency.
        """
        df = len(self.postings.get(term, ()))
        n = len(self.lengths)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def scores(self, query: str) -> dict[int, float]:
        """Score texts that share at least one term with the query.

        Each distinct query term is counted once.

        Args:
            query: Question text, tokenized with the index tokenizer.

        Returns:
            Mapping ``text index → BM25 score`` for matching texts only.
        """
        result: dict[int, float] = {}
        for term in dict.fromkeys(self.tokenizer(query)):
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = self.idf(term)
            for index, tf in postings.items():
                norm = 1 - self.b + self.b * self.lengths[index] / self.avgdl
                weight = idf * tf * (self.k1 + 1) / (tf + self.k1 * norm)
                result[index] = result.get(index, 0.0) + weight
        return result
