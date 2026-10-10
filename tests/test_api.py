import json

from django.test import Client, SimpleTestCase


class AskAPITests(SimpleTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/ask")
        self.csrf_token = self.client.cookies["csrftoken"].value

    def post(self, payload, **kwargs):
        return self.client.post(
            "/ask",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
            **kwargs,
        )

    def test_valid_question_returns_stub(self):
        response = self.post({"question": "Как поливать монстеру?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "answer": "Тестовый ответ. Поиск BM25 и LLM пока не подключены.",
                "sources": [],
            },
        )

    def test_invalid_question(self):
        for payload in ({}, {"question": ""}, {"question": " \n\t "}, {"question": None}, {"question": 123}, {"question": []}):
            with self.subTest(payload=payload):
                response = self.post(payload)
                self.assertEqual(response.status_code, 400)
                self.assertIsInstance(response.json()["error"], str)

    def test_non_object_json(self):
        for payload in ([], "question", None, 1):
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload).status_code, 400)

    def test_malformed_json(self):
        for body in (b'{"question":', b'\xff'):
            with self.subTest(body=body):
                response = self.client.post(
                    "/ask", data=body, content_type="application/json",
                    HTTP_X_CSRFTOKEN=self.csrf_token,
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json())

    def test_wrong_content_type(self):
        response = self.client.post(
            "/ask", data="question=test", content_type="text/plain",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("error", response.json())

    def test_unsupported_method(self):
        for method in ("get", "put", "delete", "patch", "options"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    "/ask", HTTP_X_CSRFTOKEN=self.csrf_token,
                )
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "POST")
                self.assertIn("error", response.json())

    def test_missing_csrf_token(self):
        response = self.client.post("/ask", {"question": "Тест"}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("error", response.json())

    def test_invalid_csrf_token(self):
        response = self.client.post(
            "/ask", {"question": "Тест"}, content_type="application/json",
            HTTP_X_CSRFTOKEN="x" * 32,
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_csrf_cookie(self):
        response = Client(enforce_csrf_checks=True).post(
            "/ask", {"question": "Тест"}, content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 403)

    def test_no_trailing_slash_redirect(self):
        response = self.client.post("/ask/", {"question": "Тест"}, content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_get_issues_csrf_cookie(self):
        response = Client(enforce_csrf_checks=True).get("/ask")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "POST")
        self.assertIn("csrftoken", response.cookies)
