"""Verify JSON validation, HTTP methods and CSRF protection."""

import json

from django.test import Client, SimpleTestCase


class AskAPITests(SimpleTestCase):
    """Exercise the application contract through a CSRF-enforcing HTTP client."""

    def setUp(self):
        """Create a CSRF-enforcing client with a bootstrap cookie."""
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/ask")
        self.csrf_token = self.client.cookies["csrftoken"].value

    def post(self, payload, **kwargs):
        """Send JSON with the bootstrap CSRF token.

        Args:
            payload: JSON-compatible request body.
            **kwargs: Additional Django client request options.

        Returns:
            The Django response for the POST request.
        """
        return self.client.post(
            "/ask",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
            **kwargs,
        )

    def test_unsupported_question_explains_demo_limit(self):
        """Return the demo limitation rather than inventing a plant answer."""
        response = self.post({"question": "Как поливать монстеру?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "answer": "Это демонстрационная версия. Выберите один из трёх примеров вопросов. Поиск по корпусу пока не подключён",
                "sources": [],
            },
        )

    def test_invalid_question(self):
        """Reject missing, blank and non-string questions."""
        for payload in (
            {},
            {"question": ""},
            {"question": " \n\t "},
            {"question": None},
            {"question": 123},
            {"question": []},
        ):
            with self.subTest(payload=payload):
                response = self.post(payload)
                self.assertEqual(response.status_code, 400)
                self.assertIsInstance(response.json()["error"], str)

    def test_non_object_json(self):
        """Reject valid JSON that is not an object."""
        for payload in ([], "question", None, 1):
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload).status_code, 400)

    def test_malformed_json(self):
        """Reject truncated JSON and invalid body encoding."""
        for body in (b'{"question":', b"\xff"):
            with self.subTest(body=body):
                response = self.client.post(
                    "/ask",
                    data=body,
                    content_type="application/json",
                    HTTP_X_CSRFTOKEN=self.csrf_token,
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json())

    def test_wrong_content_type(self):
        """Require JSON content type before parsing the body."""
        response = self.client.post(
            "/ask",
            data="question=test",
            content_type="text/plain",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("error", response.json())

    def test_unsupported_method(self):
        """Reject non-POST methods and advertise the allowed method."""
        for method in ("get", "put", "delete", "patch", "options"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    "/ask",
                    HTTP_X_CSRFTOKEN=self.csrf_token,
                )
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "POST")
                self.assertIn("error", response.json())

    def test_missing_csrf_token(self):
        """Reject POST requests without a CSRF header."""
        response = self.client.post(
            "/ask", {"question": "Тест"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("error", response.json())

    def test_invalid_csrf_token(self):
        """Reject a CSRF token that does not match the cookie."""
        response = self.client.post(
            "/ask",
            {"question": "Тест"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN="x" * 32,
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_csrf_cookie(self):
        """Reject a token without its corresponding cookie."""
        response = Client(enforce_csrf_checks=True).post(
            "/ask",
            {"question": "Тест"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 403)

    def test_no_trailing_slash_redirect(self):
        """Keep the API path exact instead of redirecting POST bodies."""
        response = self.client.post(
            "/ask/", {"question": "Тест"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

    def test_get_issues_csrf_cookie(self):
        """Issue a bootstrap cookie even when GET is rejected."""
        response = Client(enforce_csrf_checks=True).get("/ask")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "POST")
        self.assertIn("csrftoken", response.cookies)
