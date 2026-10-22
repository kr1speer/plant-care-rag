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
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        # Existing bootstrap keeps POST tests independent of the new home page.
        self.client.get("/ask")

    def ask(self, question):
        return self.client.post(
            "/ask",
            data=json.dumps({"question": question}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )

    def test_home_serves_demo_questions_and_csrf_token(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Демонстрационная версия: BM25 и LLM не подключены")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertIn("csrftoken", response.cookies)
        for question, *_ in CASES:
            self.assertContains(response, question)
        self.assertContains(response, "/static/assistant/app.js")
        self.assertContains(response, "/static/assistant/style.css")

    def test_home_cookie_allows_post(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/")
        self.assertIn("csrftoken", self.client.cookies)
        self.assertEqual(self.ask(CASES[0][0]).status_code, 200)

    def test_each_question_returns_grounded_answer_and_sources(self):
        for question, fact, title, filename in CASES:
            with self.subTest(question=question):
                response = self.ask(question)
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertIn(fact, result["answer"])
                self.assertTrue(result["sources"])
                corpus = (Path(settings.BASE_DIR) / "data/corpus" / filename).read_text()
                for source in result["sources"]:
                    self.assertEqual(set(source), {"title", "fragment", "url"})
                    self.assertEqual(source["title"], title)
                    self.assertIn(source["fragment"], corpus.split("---", 1)[1])
                    self.assertIn("Источник: " + source["url"] + "\n", corpus)

    def test_normalization_preserves_question_identity(self):
        for question, *_ in CASES:
            with self.subTest(question=question):
                variant = " \n" + question.upper().replace(" ", "  ").rstrip("?") + "!!! \t"
                self.assertEqual(self.ask(variant).json(), self.ask(question).json())
        self.assertEqual(
            self.ask("Почему у монстёры мелкие листья без прорезей.").json(),
            self.ask(CASES[0][0]).json(),
        )

    def test_unrelated_questions_never_receive_another_plant_answer(self):
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
        for asset in ("assistant/app.js", "assistant/style.css"):
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset))

    def test_home_rejects_post(self):
        response = self.client.post(
            "/", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value
        )
        self.assertEqual(response.status_code, 405)
