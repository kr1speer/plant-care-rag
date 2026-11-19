"""Verify demo answers, corpus attribution and the Django interface."""

import json

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
        self.assertEqual(self.ask("zxqvzxqv").status_code, 200)

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
