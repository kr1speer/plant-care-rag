"""Verify tokenization, fragments, the own BM25 index and retrieve()."""

import json
import math
import tempfile
from functools import partial
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from app.rag import corpus, search
from app.rag.bm25 import BM25Index
from app.rag.corpus import Fragment, load_fragments, load_registry, split_fragments
from app.rag.search import Retriever, get_default_retriever, retrieve
from app.rag.text import tokenize

RAW = partial(tokenize, stem=False, remove_stopwords=False)
LECTURE_DOCS = {
    "A": "Возврат оплаты на карту",
    "B": "Статус оплаты в приложении",
    "C": "Возврат билета через кассу",
}
LECTURE_QUESTION = "Как происходит возврат оплаты?"
RESULT_KEYS = {"doc_id", "title", "section", "fragment", "url", "score"}


def make_fragment(doc_id: str, text: str, section: str = "Раздел") -> Fragment:
    """Build an in-memory fragment indexed exactly by its text.

    Args:
        doc_id: Document identifier of the fragment.
        text: Text used both for display and for indexing.
        section: Section name of the fragment.

    Returns:
        A fragment without a title prefix in its indexed text.
    """
    return Fragment(
        doc_id=doc_id,
        title=f"Документ {doc_id}",
        section=section,
        url=f"https://example.org/{doc_id}",
        text=text,
        search_text=text,
    )


class TokenizeTests(SimpleTestCase):
    """Tokenizer normalization, stop words and stemming."""

    def test_raw_tokens_are_lowercase_words(self):
        """Lowercase, ё → е, stress marks removed, punctuation dropped."""
        self.assertEqual(
            RAW("Монсте́ра, Ёлка и 25—30 °C!"),
            ["монстера", "елка", "и", "25", "30", "c"],
        )

    def test_stop_words_and_question_words_are_removed(self):
        """Prepositions and question words do not reach the index."""
        self.assertEqual(
            tokenize("Как и почему у фикуса листья?", stem=False), ["фикуса", "листья"]
        )
        self.assertEqual(tokenize("Как и что?"), [])

    def test_stemming_joins_word_forms(self):
        """Different case forms share one stem."""
        self.assertEqual(tokenize("листья"), tokenize("листьев"))
        self.assertEqual(tokenize("клещ"), tokenize("клеща"))
        self.assertEqual(tokenize("удобрения"), tokenize("удобрение"))


class FragmentTests(SimpleTestCase):
    """Splitting a corpus file by ## and ### headings."""

    ENTRY = {"id": "D99", "file": "x.md", "title": "Растение", "url": "https://x"}
    MARKDOWN = (
        "# Растение\n\nИсточник: https://x\n\n---\n\n"
        "Вступление статьи.\n\n## Уход\nПоливать редко.\n#### Агротехника\n"
        "Подкормка весной.\n\n### Пустой\n\n### Вредители\nТля.\n"
    )

    def test_sections_become_fragments_with_prefix(self):
        """Intro, ## and ### sections; #### stays inside; empty is skipped."""
        fragments = split_fragments(self.ENTRY, self.MARKDOWN)
        self.assertEqual(
            [f.section for f in fragments], ["Вступление", "Уход", "Вредители"]
        )
        care = fragments[1]
        self.assertEqual(
            care.text, "Поливать редко.\n#### Агротехника\nПодкормка весной."
        )
        self.assertEqual(care.search_text, "Растение. Уход.\n" + care.text)
        self.assertEqual((care.doc_id, care.url), ("D99", "https://x"))
        self.assertNotIn("Источник", fragments[0].search_text)

    def test_markdown_without_separator_is_rejected(self):
        """A file without metadata separator is a corpus error."""
        with self.assertRaises(ValueError):
            split_fragments(self.ENTRY, "# Растение\nтекст")


class RegistryTests(SimpleTestCase):
    """data/documents.jsonl and its consistency checks."""

    def test_real_registry_has_thirty_documents(self):
        """IDs D01–D30 follow file numbers and match file headers."""
        registry = load_registry()
        self.assertEqual(
            [e["id"] for e in registry], [f"D{i:02d}" for i in range(1, 31)]
        )
        for entry in registry:
            with self.subTest(doc=entry["id"]):
                self.assertTrue(entry["file"].startswith(entry["id"][1:] + "_"))

    def write_corpus(self, root: Path, rows: list[dict], title: str = "Т") -> None:
        """Write a registry and one corpus file for error tests.

        Args:
            root: Temporary data directory.
            rows: Registry rows to save.
            title: Title written into the corpus file header.
        """
        (root / "corpus").mkdir()
        (root / "corpus" / "01_t.md").write_text(
            f"# {title}\n\nИсточник: https://t\n\n---\n\nТекст.\n", encoding="utf-8"
        )
        (root / "documents.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )

    def test_registry_errors_raise_value_error(self):
        """Duplicates, missing files and header mismatches are rejected."""
        good = {"id": "D01", "file": "01_t.md", "title": "Т", "url": "https://t"}
        cases = {
            "duplicate": [good, good],
            "missing file": [{**good, "file": "02_none.md"}],
            "wrong title": [{**good, "title": "Другое"}],
            "wrong url": [{**good, "url": "https://other"}],
            "bad id": [{**good, "id": "X1"}],
        }
        for name, rows in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                self.write_corpus(Path(tmp), rows)
                with self.assertRaises(ValueError):
                    load_fragments(Path(tmp))

    def test_valid_temporary_corpus_loads(self):
        """A consistent registry yields fragments with registry metadata."""
        good = {"id": "D01", "file": "01_t.md", "title": "Т", "url": "https://t"}
        with tempfile.TemporaryDirectory() as tmp:
            self.write_corpus(Path(tmp), [good])
            [fragment] = load_fragments(Path(tmp))
        self.assertEqual((fragment.doc_id, fragment.text), ("D01", "Текст."))


class BM25Tests(SimpleTestCase):
    """Own BM25 formula on the lecture example."""

    def setUp(self):
        """Index the three lecture documents without stemming and stop words."""
        self.index = BM25Index(list(LECTURE_DOCS.values()), tokenizer=RAW)

    def test_index_structure(self):
        """Inverted index stores tf per fragment, lengths and avgdl."""
        self.assertEqual(self.index.postings["возврат"], {0: 1, 2: 1})
        self.assertEqual(self.index.lengths, [4, 4, 4])
        self.assertEqual(self.index.avgdl, 4)
        self.assertAlmostEqual(self.index.idf("оплаты"), math.log(1.6))
        self.assertEqual((self.index.k1, self.index.b), (1.2, 0.75))

    def test_lecture_scores(self):
        """A 0.940, B 0.470, C 0.470 for the lecture question."""
        scores = self.index.scores(LECTURE_QUESTION)
        self.assertAlmostEqual(scores[0], 0.940, places=3)
        self.assertAlmostEqual(scores[1], 0.470, places=3)
        self.assertAlmostEqual(scores[2], 0.470, places=3)

    def test_repeated_query_word_counts_once(self):
        """Duplicates in the question do not change the score."""
        self.assertEqual(
            self.index.scores("возврат возврат оплаты"),
            self.index.scores("возврат оплаты"),
        )

    def test_length_normalization(self):
        """A longer fragment with the same tf scores lower."""
        index = BM25Index(["полив", "полив редко зимой летом"], tokenizer=RAW)
        scores = index.scores("полив")
        self.assertGreater(scores[0], scores[1])

    def test_empty_index_and_no_matches(self):
        """No fragments or no common words give no scores."""
        self.assertEqual(BM25Index([], tokenizer=RAW).scores("полив"), {})
        self.assertEqual(self.index.scores("кактус"), {})


class RetrieverTests(SimpleTestCase):
    """Ranking, ties, best fragment per document and empty results."""

    def lecture_retriever(self) -> Retriever:
        """Build a retriever over the lecture documents.

        Returns:
            Retriever without stemming and stop words.
        """
        fragments = [make_fragment(d, t) for d, t in LECTURE_DOCS.items()]
        return Retriever(fragments, tokenizer=RAW)

    def test_lecture_top_two(self):
        """With k = 2 returns A and B with lecture scores and full fields."""
        results = self.lecture_retriever().search(LECTURE_QUESTION, k=2)
        self.assertEqual([r["doc_id"] for r in results], ["A", "B"])
        self.assertAlmostEqual(results[0]["score"], 0.940, places=3)
        self.assertAlmostEqual(results[1]["score"], 0.470, places=3)
        self.assertEqual(set(results[0]), RESULT_KEYS)
        self.assertEqual(results[0]["fragment"], "Возврат оплаты на карту")

    def test_equal_scores_are_ordered_by_doc_id(self):
        """Ties are broken by doc_id regardless of corpus order."""
        fragments = [make_fragment(d, "полив летом") for d in ("D03", "D01", "D02")]
        results = Retriever(fragments, tokenizer=RAW).search("полив", k=3)
        self.assertEqual([r["doc_id"] for r in results], ["D01", "D02", "D03"])
        self.assertEqual(len({r["score"] for r in results}), 1)

    def test_one_best_fragment_per_document(self):
        """A document appears once, represented by its best fragment."""
        fragments = [
            make_fragment("D01", "полив", "Первый"),
            make_fragment("D01", "полив полив", "Лучший"),
            make_fragment("D01", "полив полив", "Позже"),
            make_fragment("D02", "полив зимой летом весной осенью", "Один"),
        ]
        results = Retriever(fragments, tokenizer=RAW).search("полив", k=3)
        self.assertEqual([r["doc_id"] for r in results], ["D01", "D02"])
        self.assertEqual(results[0]["section"], "Лучший")

    def test_empty_results(self):
        """No matching words or no tokens at all give an empty list."""
        retriever = self.lecture_retriever()
        self.assertEqual(retriever.search("кактус пустыни"), [])
        self.assertEqual(retriever.search("   ?!"), [])

    def test_invalid_k(self):
        """A depth k below one is rejected."""
        with self.assertRaises(ValueError):
            self.lecture_retriever().search(LECTURE_QUESTION, k=0)


class RealCorpusTests(SimpleTestCase):
    """retrieve() over the 30 real documents."""

    def test_retrieve_finds_expected_articles(self):
        """Characteristic questions return their article first."""
        cases = {
            "Почему у монстеры мелкие листья?": "D02",
            "Какая температура нужна фикусу бенджамина зимой?": "D03",
            "Когда пересаживать фаленопсис?": "D10",
            "Что такое хлороз растений?": "D27",
            "Какие бывают азотные удобрения?": "D30",
        }
        for question, doc_id in cases.items():
            with self.subTest(question):
                results = retrieve(question)
                self.assertEqual(results[0]["doc_id"], doc_id)
                self.assertLessEqual(len(results), 3)
                self.assertEqual(set(results[0]), RESULT_KEYS)

    def test_result_fields_match_corpus(self):
        """Fragment text, title and URL come from the registry and file."""
        registry = {e["id"]: e for e in load_registry()}
        for result in retrieve("Как размножить сансевиерию делением корневищ?", k=3):
            entry = registry[result["doc_id"]]
            path = corpus.DATA_DIR / "corpus" / entry["file"]
            with self.subTest(doc=result["doc_id"]):
                self.assertEqual(result["title"], entry["title"])
                self.assertEqual(result["url"], entry["url"])
                self.assertIn(result["fragment"], path.read_text(encoding="utf-8"))
                self.assertGreater(result["score"], 0)
        scores = [r["score"] for r in retrieve("полив зимой", k=3)]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_out_of_corpus_question_is_empty(self):
        """Words absent from the corpus give no results."""
        self.assertEqual(retrieve("квантовый блокчейн"), [])

    def test_index_is_built_once(self):
        """The default index is created lazily on the first call only."""
        get_default_retriever.cache_clear()
        with mock.patch.object(
            search, "load_fragments", wraps=search.load_fragments
        ) as loader:
            retrieve("полив")
            retrieve("свет")
        loader.assert_called_once_with()
        self.assertIs(get_default_retriever(), get_default_retriever())
