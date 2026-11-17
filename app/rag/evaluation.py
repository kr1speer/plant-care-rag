"""Benchmark metrics: Recall@k, MRR@k, Accuracy and Correct Rejection Rate."""

from collections.abc import Sequence
from statistics import fmean

VERDICTS = ("correct", "partial", "incorrect")


def recall_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    """Share of relevant documents found among the first k results.

    Args:
        retrieved: Retrieved document IDs in rank order.
        relevant: Relevant document IDs.
        k: Cut-off depth.

    Returns:
        ``|relevant ∩ top-k| / |relevant|``.

    Raises:
        ValueError: If there are no relevant documents.
    """
    if not relevant:
        raise ValueError("recall needs at least one relevant document")
    return len(set(retrieved[:k]) & set(relevant)) / len(set(relevant))


def reciprocal_rank(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    """Inverse rank of the first relevant document within the first k results.

    Args:
        retrieved: Retrieved document IDs in rank order.
        relevant: Relevant document IDs.
        k: Cut-off depth.

    Returns:
        ``1 / rank`` of the first relevant document, or 0 if none is in top-k.
    """
    relevant_set = set(relevant)
    for rank, doc_id in enumerate(retrieved[:k], 1):
        if doc_id in relevant_set:
            return 1 / rank
    return 0.0


def _share(flags: list[bool]) -> float | None:
    """Return the share of true flags, or None for an empty list.

    Args:
        flags: Boolean outcomes.

    Returns:
        Mean of the flags or None.
    """
    return sum(flags) / len(flags) if flags else None


def compute_metrics(records: Sequence[dict], k: int) -> dict:
    """Compute all benchmark metrics from result records.

    Args:
        records: Result records with ``type``, ``relevant_ids``, ``retrieved``
            (list of ``{"doc_id", "score"}``), ``refused`` and ``verdict``.
        k: Cut-off depth for retrieval metrics.

    Returns:
        Metrics keyed ``recall_at_{k}``, ``mrr_at_{k}``, ``accuracy``,
        ``accuracy_labeled``, ``correct_rejection_rate``, ``regular_total``
        and ``trap_total``. Accuracy is None until every regular question has
        a verdict; the rejection rate is None until every trap has ``refused``.

    Raises:
        ValueError: If a verdict is not one of ``VERDICTS`` or None.
    """
    regular = [r for r in records if r["type"] == "regular"]
    traps = [r for r in records if r["type"] == "trap"]
    for item in records:
        if item.get("verdict") not in (*VERDICTS, None):
            raise ValueError(f"invalid verdict: {item.get('verdict')!r}")

    def ids(item: dict) -> list[str]:
        return [hit["doc_id"] for hit in item["retrieved"]]

    recalls = [recall_at_k(ids(r), r["relevant_ids"], k) for r in regular]
    ranks = [reciprocal_rank(ids(r), r["relevant_ids"], k) for r in regular]
    labeled = [r["verdict"] for r in regular if r.get("verdict") is not None]
    refusals = [r.get("refused") for r in traps]
    return {
        f"recall_at_{k}": fmean(recalls) if recalls else None,
        f"mrr_at_{k}": fmean(ranks) if ranks else None,
        "accuracy": (
            _share([v == "correct" for v in labeled])
            if regular and len(labeled) == len(regular)
            else None
        ),
        "accuracy_labeled": len(labeled),
        "correct_rejection_rate": (
            _share([value is True for value in refusals])
            if traps and None not in refusals
            else None
        ),
        "regular_total": len(regular),
        "trap_total": len(traps),
    }
