import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from .demo import EXAMPLES
from .services import answer_question


@ensure_csrf_cookie
@require_GET
def home(request):
    return render(request, "assistant/index.html", {"examples": EXAMPLES})


@ensure_csrf_cookie
def ask(request):
    if request.method != "POST":
        response = JsonResponse({"error": "Используйте метод POST."}, status=405)
        response["Allow"] = "POST"
        return response

    if request.content_type != "application/json":
        return JsonResponse(
            {"error": "Используйте Content-Type: application/json."}, status=415
        )

    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Некорректный JSON."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "Тело запроса должно быть JSON-объектом."}, status=400)

    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        return JsonResponse({"error": "Введите непустой вопрос в поле question."}, status=400)

    return JsonResponse(answer_question(question.strip()))


def csrf_failure(request, reason=""):
    return JsonResponse(
        {"error": "Обновите главную страницу или получите CSRF-cookie через GET /ask и передайте токен в X-CSRFToken."},
        status=403,
    )
