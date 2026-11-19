"""Verify JSON validation, HTTP methods and CSRF protection."""

import json
from unittest.mock import patch
from urllib.error import HTTPError

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

    @patch("app.assistant.services.complete")
    def test_grounded_answer(self, complete):
        """Send actual BM25 fragments and return only the cited source."""
        complete.return_value = {
            "answer": "Нужен свет. [D02]",
            "refused": False,
            "sources": ["D02", "D02"],
        }
        response = self.post({"question": "Почему у монстеры листья без прорезей?"})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["refused"])
        self.assertEqual(result["answer"], "Нужен свет. [D02]")
        self.assertEqual([source["doc_id"] for source in result["sources"]], ["D02"])
        messages = complete.call_args.args[0]
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn("[D02]", messages[1]["content"])
        self.assertIn(result["sources"][0]["fragment"], messages[1]["content"])

    @patch("app.assistant.services.complete")
    def test_empty_search_skips_llm(self, complete):
        """Refuse immediately when no indexed term matches."""
        response = self.post({"question": "zxqvzxqv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "answer": "В документах нет этой информации",
                "sources": [],
                "refused": True,
            },
        )
        complete.assert_not_called()

    @patch("app.assistant.services.complete")
    def test_model_refusal(self, complete):
        """Return a refusal if the model finds insufficient evidence."""
        complete.return_value = {"answer": "", "refused": True, "sources": []}
        response = self.post({"question": "Монстера"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["refused"])
        self.assertEqual(response.json()["sources"], [])

    @patch("app.assistant.services.complete")
    def test_invalid_model_response(self, complete):
        """Report malformed or ungrounded replies as provider errors."""
        for reply in (
            {},
            {"refused": True},
            {"answer": "", "refused": True, "sources": ["D02"]},
            {"answer": "Ответ", "refused": False, "sources": ["D99"]},
            {"answer": "Ответ", "refused": False, "sources": []},
        ):
            with self.subTest(reply=reply):
                complete.return_value = reply
                response = self.post({"question": "Монстера"})
                self.assertEqual(response.status_code, 502)
                self.assertIn("error", response.json())

    def test_missing_llm_configuration(self):
        """Return a temporary service error when no provider is configured."""
        with self.settings(LLM_API_KEY="", LLM_MODEL="", LLM_BASE_URL=""):
            response = self.post({"question": "Монстера"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("недоступен", response.json()["error"])

    @patch("app.assistant.llm.build_opener")
    def test_provider_errors(self, build_opener):
        """Map timeout and rejected credentials to sanitized API errors."""
        with self.settings(
            LLM_API_KEY="test-token",
            LLM_MODEL="test-model",
            LLM_BASE_URL="http://localhost:9999/v1/",
        ):
            for error, status in (
                (TimeoutError("internal timeout"), 503),
                (HTTPError("", 401, "private provider detail", {}, None), 502),
            ):
                with self.subTest(status=status):
                    request = build_opener.return_value.open
                    request.side_effect = error
                    response = self.post({"question": "Монстера"})
                    self.assertEqual(response.status_code, status)
                    self.assertNotContains(
                        response, "private provider detail", status_code=status
                    )
                    self.assertNotContains(response, "test-token", status_code=status)
                    self.assertEqual(request.call_args.kwargs, {"timeout": 20})
                    self.assertEqual(
                        request.call_args.args[0].full_url,
                        "http://localhost:9999/v1/chat/completions",
                    )
