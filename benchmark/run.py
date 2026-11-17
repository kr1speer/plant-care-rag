"""Run the KT2 benchmark: BM25 retrieval, optional answers and metrics.

Usage from the project root::

    uv run python benchmark/run.py --retrieval-only
    uv run python benchmark/run.py
    uv run python benchmark/run.py --score benchmark/results/<file>.json
"""

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag import retrieve  # noqa: E402
from app.rag.bm25 import K1, B  # noqa: E402
from app.rag.evaluation import compute_metrics  # noqa: E402

K = 3
QUESTIONS = ROOT / "benchmark" / "questions.jsonl"
RESULTS_DIR = ROOT / "benchmark" / "results"
SCORE_DIGITS = 4

Answerer = Callable[[str], dict]


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    """Read benchmark questions from a JSON Lines file.

    Args:
        path: Path to ``questions.jsonl``.

    Returns:
        Question objects in file order.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def is_valid_answer(result: object) -> bool:
    """Check the ``answer_question`` contract expected by the benchmark.

    Args:
        result: Value returned by ``answer_question``.

    Returns:
        True for a dict with str ``answer``, list ``sources``, bool ``refused``.
    """
    return (
        isinstance(result, dict)
        and isinstance(result.get("answer"), str)
        and isinstance(result.get("sources"), list)
        and isinstance(result.get("refused"), bool)
    )


def resolve_answerer(probe_question: str) -> tuple[Answerer | None, str]:
    """Import ``answer_question`` and check its format on one question.

    Args:
        probe_question: Question used to probe the answer format.

    Returns:
        The function and an empty reason if it is compatible, otherwise None
        and the reason for falling back to retrieval-only mode.
    """
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.config.settings")
        import django

        django.setup()
        from app.assistant.services import answer_question
    except Exception as error:  # noqa: BLE001 - any import problem means fallback
        return None, f"answer_question недоступна: {type(error).__name__}: {error}"
    try:
        probe = answer_question(probe_question)
    except Exception as error:  # noqa: BLE001 - a failing service means fallback
        return None, f"answer_question завершилась ошибкой: {type(error).__name__}"
    if not is_valid_answer(probe):
        keys = sorted(probe) if isinstance(probe, dict) else type(probe).__name__
        return None, (
            "answer_question вернула другой формат: ожидаются answer, sources, "
            f"refused; получено {keys}"
        )
    return answer_question, ""


def run_benchmark(
    questions: Sequence[dict],
    retriever: Callable[..., list[dict]] = retrieve,
    answerer: Answerer | None = None,
    k: int = K,
) -> list[dict]:
    """Retrieve documents and optionally answers for every question.

    Args:
        questions: Benchmark questions.
        retriever: Function ``(question, k) → results`` like ``retrieve``.
        answerer: Compatible ``answer_question`` or None for retrieval only.
        k: Retrieval depth.

    Returns:
        Result records with retrieval output, answer fields and empty verdict.

    Raises:
        ValueError: If the answerer returns an incompatible result.
    """
    records = []
    for question in questions:
        hits = retriever(question["question"], k=k)
        answer = refused = None
        if answerer is not None:
            result = answerer(question["question"])
            if not is_valid_answer(result):
                raise ValueError(f"{question['id']}: incompatible answer format")
            answer, refused = result["answer"], result["refused"]
        records.append(
            {
                **question,
                "retrieved": [
                    {
                        "doc_id": hit["doc_id"],
                        "score": round(hit["score"], SCORE_DIGITS),
                    }
                    for hit in hits
                ],
                "answer": answer,
                "refused": refused,
                "verdict": None,
            }
        )
    return records


def result_path(results_dir: Path, day: date) -> Path:
    """Choose a new result file name without overwriting labeled results.

    Args:
        results_dir: Directory for result files.
        day: Run date used in the file name.

    Returns:
        ``<day>.json`` or the first free ``<day>-N.json``.
    """
    path = results_dir / f"{day.isoformat()}.json"
    suffix = 2
    while path.exists():
        path = results_dir / f"{day.isoformat()}-{suffix}.json"
        suffix += 1
    return path


def format_metric(value: float | None) -> str:
    """Format a metric for the summary.

    Args:
        value: Metric value or None.

    Returns:
        Value with three decimals or a dash.
    """
    return "—" if value is None else f"{value:.3f}"


def print_summary(data: dict, path: Path) -> None:
    """Print metrics and regular questions with relevant documents outside top-k.

    Args:
        data: Result file content with ``k``, ``questions`` and ``metrics``.
        path: Location of the result file.
    """
    k, metrics = data["k"], data["metrics"]
    print(f"Результаты: {path}")
    print(f"Режим: {data.get('mode', '—')}")
    if data.get("mode_reason"):
        print(f"Причина: {data['mode_reason']}")
    regular, traps = metrics["regular_total"], metrics["trap_total"]
    print(
        f"Recall@{k}: {format_metric(metrics[f'recall_at_{k}'])} ({regular} вопросов)"
    )
    print(f"MRR@{k}:    {format_metric(metrics[f'mrr_at_{k}'])}")
    print(
        f"Accuracy:  {format_metric(metrics['accuracy'])} "
        f"(размечено {metrics['accuracy_labeled']} из {regular})"
    )
    crr = format_metric(metrics["correct_rejection_rate"])
    print(f"Correct Rejection Rate: {crr} ({traps} ловушек)")
    print(f"Релевантные документы вне top-{k}:")
    misses = 0
    for item in data["questions"]:
        if item["type"] != "regular":
            continue
        found = [hit["doc_id"] for hit in item["retrieved"]]
        missing = [d for d in item["relevant_ids"] if d not in found]
        if missing:
            misses += 1
            print(
                f"  {item['id']} {item['question']}\n"
                f"      top-{k}: {', '.join(found) or '—'}; "
                f"не найдены: {', '.join(missing)}"
            )
    if not misses:
        print("  нет")


def write_json(path: Path, data: dict) -> None:
    """Save a result file as readable UTF-8 JSON.

    Args:
        path: Target file.
        data: JSON-compatible content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def score_file(path: Path) -> dict:
    """Recompute metrics of a saved result file after manual labeling.

    Args:
        path: Result file produced by a benchmark run.

    Returns:
        Updated file content; the file is rewritten with new metrics.

    Raises:
        ValueError: If a verdict is invalid.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    data["metrics"] = compute_metrics(data["questions"], data["k"])
    write_json(path, data)
    return data


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Arguments without the program name, or None for ``sys.argv``.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Benchmark поиска BM25 и ответов.")
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="только поиск, без answer_question",
    )
    parser.add_argument(
        "--score", type=Path, metavar="FILE", help="пересчитать метрики файла"
    )
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument(
        "--date", type=date.fromisoformat, default=None, help="дата в имени файла"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark or rescore a labeled result file.

    Args:
        argv: Arguments without the program name, or None for ``sys.argv``.

    Returns:
        Process exit code: 0 on success, 2 on invalid result data.
    """
    args = parse_args(argv)
    if args.score:
        try:
            data = score_file(args.score)
        except ValueError as error:
            print(f"Ошибка разметки verdict: {error}", file=sys.stderr)
            return 2
        print_summary(data, args.score)
        return 0

    questions = load_questions(args.questions)
    answerer, reason = (None, "задан --retrieval-only")
    if not args.retrieval_only:
        answerer, reason = resolve_answerer(questions[0]["question"])
        if answerer is None:
            print(f"Предупреждение: режим retrieval-only. {reason}", file=sys.stderr)
    records = run_benchmark(questions, answerer=answerer)
    data = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "full" if answerer else "retrieval-only",
        "mode_reason": reason,
        "k": K,
        "bm25": {"k1": K1, "b": B},
        "questions": records,
        "metrics": compute_metrics(records, K),
    }
    path = result_path(args.results_dir, args.date or date.today())
    write_json(path, data)
    print_summary(data, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
