"""Call an OpenAI-compatible Chat Completions endpoint."""

import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings


class LLMError(Exception):
    """Represent an invalid or rejected response from the LLM provider."""

    status = 502
    message = "Сервис LLM отклонил запрос или вернул некорректный ответ."


class LLMUnavailable(LLMError):
    """Represent missing configuration or temporarily unavailable service."""

    status = 503
    message = "Сервис LLM временно недоступен. Попробуйте позже."


class NoRedirect(HTTPRedirectHandler):
    """Keep the authenticated request on the configured endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Decline redirects so credentials stay on the configured endpoint.

        Args:
            req: Original request.
            fp: Redirect response stream.
            code: HTTP status.
            msg: HTTP reason.
            headers: Response headers.
            newurl: Redirect destination.

        Returns:
            None, which makes urllib handle the redirect as an HTTP error.
        """
        return None


def complete(messages: list[dict[str, str]]) -> object:
    """Send the messages and decode the model's JSON content.

    Args:
        messages: System and user messages for Chat Completions.

    Returns:
        The decoded JSON value from the first completion.

    Raises:
        LLMError: If the provider rejects the request or returns invalid data.
        LLMUnavailable: If configuration is missing or the provider is unavailable.
    """
    base_url = settings.LLM_BASE_URL.rstrip("/")
    try:
        endpoint = urlsplit(base_url)
    except ValueError:
        raise LLMUnavailable from None
    if (
        not settings.LLM_API_KEY
        or not settings.LLM_MODEL
        or endpoint.scheme not in {"http", "https"}
        or not endpoint.hostname
        or endpoint.username is not None
        or endpoint.query
        or endpoint.fragment
    ):
        raise LLMUnavailable

    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps({"model": settings.LLM_MODEL, "messages": messages}).encode(),
        headers={
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            completion = json.load(response)
        return json.loads(completion["choices"][0]["message"]["content"])
    except HTTPError as error:
        error.close()
        if error.code in {408, 429} or error.code >= 500:
            raise LLMUnavailable from None
        raise LLMError from None
    except (TimeoutError, URLError, OSError, HTTPException):
        raise LLMUnavailable from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError from None
