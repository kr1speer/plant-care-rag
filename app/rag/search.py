"""Document ranking on top of BM25 fragments and the public retrieve()."""

from collections.abc import Sequence
from functools import cache

from .bm25 import K1, B, BM25Index, Tokenizer
from .corpus import Fragment, load_fragments
from .text import tokenize

DEFAULT_K = 3


class Retriever:
    """Rank documents by the BM25 score of their best fragment."""

    def __init__(
        self,
        fragments: Sequence[Fragment],
        tokenizer: Tokenizer = tokenize,
        k1: float = K1,
        b: float = B,
    ) -> None:
        """Index fragment search texts.

        Args:
            fragments: Fragments to search; order breaks ties inside a document.
            tokenizer: Function that turns text into tokens.
            k1: BM25 term frequency saturation parameter.
            b: BM25 length normalization parameter.
        """
        self.fragments = list(fragments)
        self.index = BM25Index(
            [fragment.search_text for fragment in self.fragments], tokenizer, k1, b
        )

    def search(self, question: str, k: int = DEFAULT_K) -> list[dict]:
        """Return the top-k documents for a question.

        Args:
            question: User question.
            k: Maximum number of documents to return.

        Returns:
            Up to ``k`` result dicts with ``doc_id``, ``title``, ``section``,
            ``fragment``, ``url`` and ``score``, sorted by score descending
            and then by ``doc_id``; empty if nothing matches.

        Raises:
            ValueError: If ``k`` is less than 1.
        """
        if k < 1:
            raise ValueError("k must be at least 1")
        best: dict[str, tuple[float, Fragment]] = {}
        for index, score in sorted(self.index.scores(question).items()):
            fragment = self.fragments[index]
            current = best.get(fragment.doc_id)
            if current is None or score > current[0]:
                best[fragment.doc_id] = (score, fragment)
        ranked = sorted(best.items(), key=lambda item: (-item[1][0], item[0]))
        return [
            {
                "doc_id": doc_id,
                "title": fragment.title,
                "section": fragment.section,
                "fragment": fragment.text,
                "url": fragment.url,
                "score": score,
            }
            for doc_id, (score, fragment) in ranked[:k]
        ]


@cache
def get_default_retriever() -> Retriever:
    """Build the corpus index on first use and reuse it afterwards.

    Returns:
        Retriever over all fragments of ``data/``.
    """
    return Retriever(load_fragments())


def retrieve(question: str, k: int = DEFAULT_K) -> list[dict]:
    """Find the top-k corpus documents for a question with BM25.

    Args:
        question: User question.
        k: Maximum number of documents to return.

    Returns:
        Up to ``k`` results, one best fragment per document; see
        ``Retriever.search`` for fields and order.

    Raises:
        ValueError: If ``k`` is less than 1 or the corpus registry is invalid.
    """
    return get_default_retriever().search(question, k)
