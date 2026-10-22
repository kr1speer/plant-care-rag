"""Verify demo answers, corpus attribution and the Django interface."""

import json
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client, SimpleTestCase

CASES = (
    (
        "Почему у монстеры мелкие листья без прорезей?",
        "недостатком света",
        "Монстера деликатесная",
        "02_monstera.md",
    ),
    (
        "Какая температура нужна фикусу Бенджамина летом и зимой?",
        "25–30 °C",
        "Фикус бенджамина",
        "03_fikus-benjamina.md",
    ),
    (
        "Когда и как пересаживать орхидею фаленопсис?",
        "раз в год после цветения",
        "Фаленопсис",
        "10_falenopsis.md",
    ),
)


class DemoTests(SimpleTestCase):
    """Exercise the application contract through a CSRF-enforcing HTTP client."""

    def setUp(self):
        """Create a CSRF-enforcing client with a bootstrap cookie."""
        self.client = Client(enforce_csrf_checks=True)
        # Existing bootstrap keeps POST tests independent of the new home page.
        self.client.get("/ask")

    def ask(self, question):
        """Send a question through the CSRF-protected API.

        Args:
            question: Question string included in the JSON body.

        Returns:
            The Django response for the question.
        """
        return self.client.post(
            "/ask",
            data=json.dumps({"question": question}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )

    def test_home_serves_demo_questions_and_csrf_token(self):
        """Serve the supported examples, token and namespaced asset references."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Демонстрационная версия: BM25 и LLM не подключены"
        )
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertIn("csrftoken", response.cookies)
        for question, *_ in CASES:
            self.assertContains(response, question)
        self.assertContains(response, "/static/assistant/app.js")
        self.assertContains(response, "/static/assistant/style.css")

    def test_home_cookie_allows_post(self):
        """Accept an API request bootstrapped through the home page."""
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/")
        self.assertIn("csrftoken", self.client.cookies)
        self.assertEqual(self.ask(CASES[0][0]).status_code, 200)

    def test_each_question_returns_grounded_answer_and_sources(self):
        """Match each answer and source excerpt against the saved corpus."""
        for question, fact, title, filename in CASES:
            with self.subTest(question=question):
                response = self.ask(question)
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertIn(fact, result["answer"])
                self.assertTrue(result["sources"])
                corpus = (
                    Path(settings.BASE_DIR) / "data/corpus" / filename
                ).read_text()
                for source in result["sources"]:
                    self.assertEqual(set(source), {"title", "fragment", "url"})
                    self.assertEqual(source["title"], title)
                    self.assertIn(source["fragment"], corpus.split("---", 1)[1])
                    self.assertIn("Источник: " + source["url"] + "\n", corpus)

    def test_normalization_preserves_question_identity(self):
        """Normalize cosmetic input changes without changing the selected example."""
        for question, *_ in CASES:
            with self.subTest(question=question):
                variant = (
                    " \n" + question.upper().replace(" ", "  ").rstrip("?") + "!!! \t"
                )
                self.assertEqual(self.ask(variant).json(), self.ask(question).json())
        self.assertEqual(
            self.ask("Почему у монстёры мелкие листья без прорезей.").json(),
            self.ask(CASES[0][0]).json(),
        )

    def test_unrelated_questions_never_receive_another_plant_answer(self):
        """Reject substring matches that previously selected unrelated answers."""
        for question in (
            "Как поливать орхидею?",
            "Когда пересаживать фикус?",
            "Как вырастить помидоры на балконе?",
            "Какое освещение нужно монстере?",
        ):
            with self.subTest(question=question):
                response = self.ask(question)
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertEqual(result["sources"], [])
                self.assertIn("Выберите один из трёх примеров", result["answer"])

    def test_assets_are_discoverable_by_django(self):
        """Keep referenced assets discoverable in both local and container runs."""
        for asset in ("assistant/app.js", "assistant/style.css"):
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset))

    def test_home_rejects_post(self):
        """Keep the home page read-only for CSRF-valid requests."""
        response = self.client.post(
            "/", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value
        )
        self.assertEqual(response.status_code, 405)
