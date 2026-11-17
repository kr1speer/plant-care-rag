"""Verify benchmark questions, evidence quotes, metrics and benchmark/run.py."""

import importlib.util
import io
import json
import re
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from app.rag.corpus import load_registry
from app.rag.evaluation import compute_metrics, recall_at_k, reciprocal_rank

ROOT = Path(settings.BASE_DIR)
QUESTIONS = ROOT / "benchmark" / "questions.jsonl"
EVIDENCE = ROOT / "benchmark" / "evidence.md"
REFUSAL = "В документах нет этой информации"


def load_run_module():
    """Import benchmark/run.py, which is a script outside the app package.

    Returns:
        The loaded module object.
    """
    spec = importlib.util.spec_from_file_location(
        "benchmark_run", ROOT / "benchmark" / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_questions() -> list[dict]:
    """Read all benchmark questions.

    Returns:
        Question objects in file order.
    """
    lines = QUESTIONS.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def record(qtype: str, relevant: list[str], retrieved: list[str], **extra) -> dict:
    """Build a result record for metric tests.

    Args:
        qtype: ``regular`` or ``trap``.
        relevant: Relevant document IDs.
        retrieved: Retrieved document IDs in rank order.
        **extra: Answer fields such as ``refused`` or ``verdict``.

    Returns:
        A record in the benchmark result format.
    """
    return {
        "type": qtype,
        "relevant_ids": relevant,
        "retrieved": [{"doc_id": d, "score": 1.0} for d in retrieved],
        "refused": extra.get("refused"),
        "verdict": extra.get("verdict"),
    }


class QuestionFileTests(SimpleTestCase):
    """benchmark/questions.jsonl follows the KT2 format."""

    def test_composition_and_fields(self):
        """15 questions: 10 regular with ≥3 known relevant IDs and 5 traps."""
        questions = read_questions()
        known = {e["id"] for e in load_registry()}
        self.assertEqual([q["id"] for q in questions], [f"Q{i:02d}" for i in range(1, 16)])
        self.assertEqual(sum(q["type"] == "regular" for q in questions), 10)
        self.assertEqual(sum(q["type"] == "trap" for q in questions), 5)
        for q in questions:
            with self.subTest(q["id"]):
                self.assertEqual(
                    set(q),
                    {"id", "question", "relevant_ids", "expected_answer", "type"},
                )
                self.assertTrue(q["question"].strip())
                if q["type"] == "regular":
                    self.assertGreaterEqual(len(set(q["relevant_ids"])), 3)
                    self.assertEqual(len(set(q["relevant_ids"])), len(q["relevant_ids"]))
                    self.assertLessEqual(set(q["relevant_ids"]), known)
                    self.assertNotEqual(q["expected_answer"], REFUSAL)
                else:
                    self.assertEqual(q["type"], "trap")
                    self.assertEqual(q["relevant_ids"], [])
                    self.assertEqual(q["expected_answer"], REFUSAL)

    def test_evidence_quotes_are_verbatim(self):
        """Every relevant document has a quote that occurs in its text."""
        files = {e["id"]: e["file"] for e in load_registry()}
        quotes: dict[str, dict[str, list[str]]] = {}
        current = None
        for line in EVIDENCE.read_text(encoding="utf-8").splitlines():
            if heading := re.fullmatch(r"## (Q\d\d)", line.strip()):
                current = heading.group(1)
                quotes[current] = {}
            elif (item := re.fullmatch(r"- (D\d\d): «(.+)»", line.strip())) and current:
                quotes[current].setdefault(item.group(1), []).append(item.group(2))
        for q in read_questions():
            if q["type"] != "regular":
                continue
            with self.subTest(q["id"]):
                self.assertEqual(set(quotes[q["id"]]), set(q["relevant_ids"]))
                for doc_id, doc_quotes in quotes[q["id"]].items():
                    path = ROOT / "data" / "corpus" / files[doc_id]
                    body = path.read_text(encoding="utf-8").split("\n---\n", 1)[1]
                    for quote in doc_quotes:
                        self.assertIn(quote, body, f"{doc_id}: {quote}")


class MetricTests(SimpleTestCase):
    """Recall@k, MRR@k, Accuracy and Correct Rejection Rate."""

    def test_recall_and_reciprocal_rank(self):
        """Only the first k retrieved documents count."""
        relevant = ["D01", "D02", "D03", "D04"]
        self.assertEqual(recall_at_k(["D09", "D02", "D01", "D03"], relevant, 3), 0.5)
        self.assertEqual(reciprocal_rank(["D09", "D02", "D01"], relevant, 3), 0.5)
        self.assertEqual(reciprocal_rank(["D09", "D08", "D07", "D01"], relevant, 3), 0)
        self.assertEqual(recall_at_k([], relevant, 3), 0)
        with self.assertRaises(ValueError):
            recall_at_k(["D01"], [], 3)

    def test_compute_metrics(self):
        """Regular questions give retrieval metrics, traps give CRR."""
        records = [
            record("regular", ["D01", "D02"], ["D01", "D02", "D05"], verdict="correct"),
            record("regular", ["D03", "D04"], ["D05", "D04"], verdict="partial"),
            record("trap", [], ["D01"], refused=True),
            record("trap", [], [], refused=False),
        ]
        metrics = compute_metrics(records, k=3)
        self.assertEqual(metrics["recall_at_3"], 0.75)
        self.assertEqual(metrics["mrr_at_3"], 0.75)
        self.assertEqual(metrics["accuracy"], 0.5)
        self.assertEqual(metrics["accuracy_labeled"], 2)
        self.assertEqual(metrics["correct_rejection_rate"], 0.5)
        self.assertEqual((metrics["regular_total"], metrics["trap_total"]), (2, 2))

    def test_unlabeled_and_retrieval_only_metrics_are_null(self):
        """Missing verdicts or refusals leave Accuracy and CRR undefined."""
        records = [
            record("regular", ["D01"], ["D01"], verdict="correct"),
            record("regular", ["D02"], ["D01"]),
            record("trap", [], []),
        ]
        metrics = compute_metrics(records, k=3)
        self.assertIsNone(metrics["accuracy"])
        self.assertEqual(metrics["accuracy_labeled"], 1)
        self.assertIsNone(metrics["correct_rejection_rate"])

    def test_invalid_verdict_is_rejected(self):
        """Only correct, partial, incorrect or null are allowed."""
        with self.assertRaises(ValueError):
            compute_metrics([record("regular", ["D01"], [], verdict="ok")], k=3)


class RunScriptTests(SimpleTestCase):
    """benchmark/run.py end to end with a temporary results directory."""

    def setUp(self):
        """Load the script module."""
        self.run = load_run_module()

    def call_main(self, *argv: str) -> tuple[int, str, str]:
        """Run main() and capture its output.

        Args:
            *argv: Command-line arguments.

        Returns:
            Exit code, standard output and standard error.
        """
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.run.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_retrieval_only_run_and_rescore(self):
        """A run saves results and --score recomputes metrics after labeling."""
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self.call_main(
                "--retrieval-only", "--results-dir", tmp, "--date", "2026-11-17"
            )
            self.assertEqual(code, 0)
            path = Path(tmp) / "2026-11-17.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "retrieval-only")
            self.assertEqual((data["k"], data["bm25"]), (3, {"k1": 1.2, "b": 0.75}))
            self.assertEqual(len(data["questions"]), 15)
            first = data["questions"][0]
            self.assertLessEqual(len(first["retrieved"]), 3)
            self.assertEqual(set(first["retrieved"][0]), {"doc_id", "score"})
            self.assertIsNone(first["answer"])
            self.assertIsNone(first["verdict"])
            self.assertIsNone(data["metrics"]["correct_rejection_rate"])
            self.assertIn("Recall@3", out)
            self.assertIn("MRR@3", out)

            code, _, _ = self.call_main(
                "--retrieval-only", "--results-dir", tmp, "--date", "2026-11-17"
            )
            self.assertTrue((Path(tmp) / "2026-11-17-2.json").exists())

            for item in data["questions"]:
                item["verdict"] = "correct" if item["type"] == "regular" else None
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            code, out, _ = self.call_main("--score", str(path))
            self.assertEqual(code, 0)
            rescored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(rescored["metrics"]["accuracy"], 1.0)
            self.assertIn("Accuracy", out)

    def test_score_rejects_bad_verdict(self):
        """An invalid manual label stops rescoring with an error."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            questions = [record("regular", ["D01"], ["D01"], verdict="да")]
            path.write_text(json.dumps({"k": 3, "questions": questions}), "utf-8")
            code, _, err = self.call_main("--score", str(path))
        self.assertEqual(code, 2)
        self.assertIn("verdict", err)

    def test_answer_question_format_detection(self):
        """Only {"answer", "sources", "refused"} enables the full mode."""
        valid = {"answer": "Да", "sources": [], "refused": False}
        self.assertTrue(self.run.is_valid_answer(valid))
        for bad in ({"answer": "Да", "sources": []}, {**valid, "refused": "no"}, None):
            with self.subTest(bad=bad):
                self.assertFalse(self.run.is_valid_answer(bad))

    def test_current_service_falls_back_to_retrieval_only(self):
        """The KT1 demo service has no refused field and is not used."""
        answerer, reason = self.run.resolve_answerer("Вопрос?")
        self.assertIsNone(answerer)
        self.assertIn("формат", reason)

    def test_full_mode_records_answers(self):
        """A compatible answerer fills answer and refused fields."""

        def fake(question: str) -> dict:
            refused = "монстер" in question
            return {"answer": REFUSAL if refused else "Ответ", "sources": [], "refused": refused}

        questions = [q for q in read_questions() if q["id"] in {"Q01", "Q11"}]
        records = self.run.run_benchmark(questions, answerer=fake)
        self.assertEqual([r["refused"] for r in records], [False, True])
        self.assertEqual(records[0]["answer"], "Ответ")
        with self.assertRaises(ValueError):
            self.run.run_benchmark(questions, answerer=lambda q: {"answer": "x"})

    def test_result_path_never_overwrites(self):
        """Existing result files get numeric suffixes."""
        with tempfile.TemporaryDirectory() as tmp:
            first = self.run.result_path(Path(tmp), date(2026, 11, 17))
            first.write_text("{}", encoding="utf-8")
            second = self.run.result_path(Path(tmp), date(2026, 11, 17))
        self.assertEqual((first.name, second.name), ("2026-11-17.json", "2026-11-17-2.json"))
