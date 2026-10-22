# Зелёный помощник

Учебный проект НИРС 2026: помощник по уходу за комнатными растениями для человека без опыта ухода. Целевой сценарий: вопрос → найденные фрагменты статей → ответ LLM с источниками.

## Состояние КТ №1

Реализована демонстрация в одном Django-приложении: главная страница → `POST /ask` → подготовленный ответ → источники. Доступны три примера; остальные вопросы получают сообщение об ограничении демонстрации. **BM25 и LLM не подключены.** База данных, регистрация и ключи LLM не нужны. Корпус из 28 статей и набор вопросов benchmark подготовлены для следующего этапа.

Комплект для проверки:

- [Продукт, пользователь и границы](spec/product/product.md).
- [Сценарии и ожидаемое поведение](spec/product/scenarios.md).
- [Архитектура и контракт API](spec/tech/architecture.md).
- [Корпус и проект будущего RAG/benchmark](spec/tech/rag.md).
- [Все требования КТ №1, замечания преподавателя, результаты и пакет сдачи](spec/product/kt1.md).
- [Задачи, зависимости и ответственные](spec/tech/tasks.md).
- Исходники интерфейса: [HTML](app/assistant/templates/assistant/index.html), [JavaScript](app/assistant/static/assistant/app.js), [CSS](app/assistant/static/assistant/style.css).
- [История изменений и проверок](CHANGE_HISTORY.md), [правила работы](AGENTS.md).

## Команда и роли

| Участник | Роль | Зона ответственности |
|---|---|---|
| Акопов Антон | BM25 и RAG | Корпус, фрагменты, индекс, поиск, benchmark и метрики; проверка источников демонстрации |
| Кунев Валентин | Интеграция | Django, связь интерфейса и API, будущий вызов LLM, тесты API и запуск |
| Гаранин Ерофей | Продукт и интерфейс | Пользователь, задача, сценарии, внешний вид и браузерная проверка |

Зоны постоянные. Каждый участник должен понимать путь запроса и уметь запускать проект; личное подтверждение фиксируется в приёмке, а не предполагается из наличия инструкции.

## Структура

```text
app/
  config/                  настройки Django и маршруты
  assistant/
    views.py               HTML-страница, API, CSRF-ошибки
    services.py            сопоставление демонстрационных вопросов
    demo.py                единый набор вопросов, ответов и источников
    templates/assistant/   HTML
    static/assistant/      CSS и JavaScript
spec/product/              пользователь, сценарии, приёмка и скриншоты
spec/tech/                 архитектура, планы RAG и задачи
data/corpus/               28 статей
benchmark/questions.jsonl  вопросы и эталонные ответы будущего benchmark
tests/                     API-тесты и браузерный сценарий
manage.py                  команды Django
pyproject.toml, uv.lock     зависимости Python 3.13 / Django 5.2
Dockerfile, compose.yaml   контейнерный запуск
```

## Запуск из свежего клона

```bash
git clone https://github.com/kr1speer/plant-care-rag.git
cd plant-care-rag
```

Исправления доступны в клоне только после их публикации в выбранной ветке. Сверяйте SHA и статус публикации в [приёмке](spec/product/kt1.md). Сейчас результаты приёмки описывают локальную рабочую версию.

Все следующие команды выполняются из корня проекта. Запускайте uv и Compose по очереди: оба используют порт 8000.

### Через uv

Установите [uv](https://docs.astral.sh/uv/getting-started/installation/), затем:

```bash
uv run python manage.py runserver
```

uv подготовит Python 3.13, `.venv` и закреплённые зависимости из `uv.lock`. При первой установке нужен доступ к сети. Откройте **http://localhost:8000/** — это интерфейс, а не `/ask`. Остановка: Ctrl+C.

### Через Docker Compose

Нужен работающий Docker с Compose. В Windows/WSL включите интеграцию дистрибуции в Docker Desktop (Settings → Resources → WSL Integration).

```bash
docker compose up --build
```

Откройте **http://localhost:8000/**. Остановка: Ctrl+C; удаление контейнера и сети проекта:

```bash
docker compose down
```

При первой сборке нужен доступ к реестрам образов и зависимостям. Контейнер использует `uv.lock`; включает статьи для проверки соответствия источников. Это локальная разработка с DEBUG и runserver, порт опубликован только на loopback.

Если в WSL команда `docker` сообщает об отсутствии интеграции, исправьте настройку Docker Desktop. Не считайте такой результат ошибкой API или успешной контейнерной проверкой. Диагностика: `docker version`, `docker compose version`.

## Основной сценарий демонстрации

1. Откройте `/`, убедитесь в наличии пометки о демонстрационной версии.
2. Выберите вопрос о мелких листьях монстеры и нажмите «Спросить»: ответ о недостатке света, фрагмент и ссылка на статью.
3. Повторите для температуры фикуса: 25–30 °C летом, 16–20 °C зимой, не ниже 14 °C.
4. Повторите для пересадки фаленопсиса: согласно статье корпуса, раз в год после цветения, субстрат из сосновой коры.
5. Введите «Как поливать орхидею?»: сообщение о трёх доступных примерах, источников нет; ответ о монстере не подставляется.
6. Проверьте пробелы, повторный вопрос, клавиатуру и восстановление формы после сетевой ошибки. Полный список — в [сценариях](spec/product/scenarios.md).

При ответе приложение не выполняет поиск и не обращается к Википедии или LLM. Ссылки ведут к исходным статьям; фрагменты сверяются с сохранённым корпусом. Точные формулировки трёх вопросов можно вводить с другим регистром, пробелами, ё/е и завершающими `?!.`.

## Проверка API

Эндпоинт — `POST /ask`, без завершающего слеша. Сначала получите CSRF-cookie через `GET /` или совместимый `GET /ask` (возвращает 405). Пример для Bash:

```bash
COOKIE_FILE=$(mktemp)
curl -fsS -c "$COOKIE_FILE" http://localhost:8000/ -o /dev/null
CSRF_TOKEN=$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_FILE")
curl -fsS -b "$COOKIE_FILE" \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  --data '{"question":"Почему у монстеры мелкие листья без прорезей?"}' \
  http://localhost:8000/ask
rm "$COOKIE_FILE"
```

Ожидаются HTTP 200, строка `answer` о недостатке света и непустой `sources` с `title`, `fragment`, `url`. Неподдерживаемый вопрос тоже возвращает 200, но с сообщением об ограничении демонстрации и `sources: []`. Полный контракт и ошибки — в [архитектуре](spec/tech/architecture.md).

## Проверки

```bash
uv run python manage.py check
uv run python manage.py test tests
node --check app/assistant/static/assistant/app.js
git diff --check
```

В запущенном контейнере:

```bash
docker compose exec -T web uv run --no-sync python manage.py check
docker compose exec -T web uv run --no-sync python manage.py test tests
```

Дополнительная автоматическая проверка настоящим Chromium (Node.js >=20, установка инструментов вне репозитория; команды для Linux/WSL):

```bash
npm install --prefix /tmp/plant-care-browser playwright@1.64.1
PLAYWRIGHT_BROWSERS_PATH=/tmp/plant-care-browsers \
  node /tmp/plant-care-browser/node_modules/playwright/cli.js install chromium
NODE_PATH=/tmp/plant-care-browser/node_modules \
  PLAYWRIGHT_BROWSERS_PATH=/tmp/plant-care-browsers \
  node tests/browser.cjs
```

Сервер uv или Compose должен быть запущен. При отсутствии системных библиотек Chromium используйте штатный `playwright install-deps chromium` в своей среде; это может требовать прав администратора. `BASE_URL` меняет адрес сервера, `ARTIFACT_DIR` — каталог скриншотов (по умолчанию `/tmp/plant-care-evidence`). Скрипт проверяет сценарии, HTTP/сетевые ошибки, безопасность вывода и ширины 375/1280 px. Benchmark RAG пока не запускается.

Фактические результаты, скриншоты и оставшиеся шаги публикации — в [приёмке КТ №1](spec/product/kt1.md).
