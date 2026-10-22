"""KT1 demonstration. Replace exact fixture lookup with BM25 → LLM later."""

from .demo import EXAMPLES, UNSUPPORTED_ANSWER


def normalize_question(question: str) -> str:
    return " ".join(question.lower().replace("ё", "е").split()).rstrip("?!.").rstrip()


def answer_question(question: str) -> dict:
    normalized = normalize_question(question)
    for example in EXAMPLES:
        if normalized == normalize_question(example["question"]):
            return {
                "answer": example["answer"],
                "sources": [dict(source) for source in example["sources"]],
            }
    return {"answer": UNSUPPORTED_ANSWER, "sources": []}
