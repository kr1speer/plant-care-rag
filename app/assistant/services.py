"""KT1 demonstration. Replace exact fixture lookup with BM25 → LLM later."""

from .demo import EXAMPLES, UNSUPPORTED_ANSWER


def normalize_question(question: str) -> str:
    """Normalize a supported question without fuzzy or substring matching.

    Args:
        question: User input to normalize.

    Returns:
        Lowercase text with collapsed whitespace, normalized ё and no final ?!.
    """
    return " ".join(question.lower().replace("ё", "е").split()).rstrip("?!.").rstrip()


def answer_question(question: str) -> dict:
    """Return a prepared answer or the explicit demonstration limitation.

    Args:
        question: Nonempty question already validated by the API.

    Returns:
        A JSON-compatible mapping with answer and fresh copies of sources.
    """
    normalized = normalize_question(question)
    for example in EXAMPLES:
        if normalized == normalize_question(example["question"]):
            return {
                "answer": example["answer"],
                "sources": [dict(source) for source in example["sources"]],
            }
    return {"answer": UNSUPPORTED_ANSWER, "sources": []}
