# Зелёный помощник

[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django 5.2.18](https://img.shields.io/badge/Django-5.2.18-092E20?logo=django&logoColor=white)](https://docs.djangoproject.com/en/5.2/)
[![CI](https://github.com/kr1speer/plant-care-rag/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/kr1speer/plant-care-rag/actions/workflows/ci.yaml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue)](LICENSE)

Учебный проект НИРС 2026: веб-помощник по уходу за комнатными растениями для человека без опыта. Цель — получать понятные ответы и проверять их по исходным статьям.

## История КТ №1 и текущий API

На КТ №1 работала демонстрация в одном Django-приложении:

```text
Главная страница → вопрос → POST /ask → подготовленный ответ → источники
```

На КТ №2 `POST /ask` принимает произвольный вопрос, ищет по корпусу из 30 статей и возвращает ответ LLM с источниками или явный отказ. Три вопроса КТ №1 остаются подсказками. Интерфейс показывает ответ с источниками или отдельное состояние отказа; сценарии — [scenarios.md](spec/product/scenarios.md), приёмка — [kt2.md](spec/product/kt2.md).

Примеры и ожидаемые ответы демонстрации КТ №1:

| Вопрос                                                   | Ожидаемый ответ                                                              |
| -------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Почему у монстеры мелкие листья без прорезей?            | Недостаток света                                                             |
| Какая температура нужна фикусу Бенджамина летом и зимой? | Летом 25–30 °C, зимой 16–20 °C, не ниже 14 °C                                |
| Когда и как пересаживать орхидею фаленопсис?             | Согласно статье корпуса, раз в год после цветения, субстрат из сосновой коры |

Доказательства первой сдачи сохранены в [приёмке КТ №1](spec/product/kt1.md).

## Команда

| Участник       | Постоянная роль     | Ответственность                                               |
| -------------- | ------------------- | ------------------------------------------------------------- |
| Акопов Антон   | BM25 и RAG          | Корпус, фрагменты, поиск, benchmark и метрики                 |
| Кунев Валентин | Интеграция          | Django, связь интерфейса и API, вызов LLM, тесты и запуск     |
| Гаранин Ерофей | Продукт и интерфейс | Пользователь, задача, сценарии, вёрстка и браузерная проверка |

Каждый участник должен понимать путь запроса и уметь запускать проект. Личное подтверждение и статус сдачи фиксируются в [приёмке КТ №1](spec/product/kt1.md).

## Стек и основные зависимости

Версии библиотек ниже соответствуют lock-файлам, а не всем допустимым версиям из манифестов.

| Компонент                   | Версия                   | Назначение                                                   |
| --------------------------- | ------------------------ | ------------------------------------------------------------ |
| Python                      | 3.13                     | Выполнение приложения                                        |
| Django                      | 5.2.18                   | Интерфейс, API и тесты                                       |
| python-dotenv               | 1.2.4                    | Загрузка локальной конфигурации                              |
| snowballstemmer             | 3.1.1                    | Русский стемминг для BM25                                    |
| uv                          | 0.9.3 в контейнере и CI  | Установка Python-зависимостей; локально нужен совместимый uv |
| Node.js                     | 24                       | Только инструменты разработки и браузерные тесты             |
| Ruff / coverage.py / djLint | 0.17.1 / 7.16.2 / 1.47.0 | Стиль Python, покрытие, Django HTML                          |
| ESLint / Prettier           | 10.13.0 / 3.9.10         | Проверка JS и форматирование                                 |
| Playwright Test             | 1.64.1                   | Проверки интерфейса в Chromium                               |

Python-зависимости закреплены в `uv.lock`, инструменты Node — в `package-lock.json`. Для обычного запуска Django Node.js не требуется; для контейнерного запуска не нужны локальные Python и uv.

## Структура и документация

```text
app/config/                   настройки и маршруты Django
app/assistant/                страница, API, сервис и демо-данные
app/rag/                      собственный BM25-поиск и метрики benchmark
  templates/assistant/        HTML интерфейса
  static/assistant/           JavaScript и CSS
spec/product/                 продукт, сценарии, приёмка и доказательства
spec/tech/                    архитектура, задачи, качество и план RAG
data/corpus/                  30 справочных статей
data/documents.jsonl          реестр документов D01–D30
benchmark/                    вопросы, цитаты, run.py и results/
tests/                        Django-тесты и сценарии Playwright
.github/workflows/ci.yaml      автоматические проверки GitHub
.env.example                  шаблон конфигурации без секретов
pyproject.toml, uv.lock        зависимости и Python-инструменты
package.json, package-lock.json инструменты Node
Dockerfile, docker-compose.yaml контейнерный запуск
```

- [Продукт, пользователь и границы](spec/product/product.md), [сценарии](spec/product/scenarios.md).
- [Архитектура и контракт API](spec/tech/architecture.md), [корпус и план RAG](spec/tech/rag.md).
- [Задачи и ответственные](spec/tech/tasks.md), [качество и CI](spec/tech/quality.md).
- [Все требования КТ №1 и результаты проверок](spec/product/kt1.md).
- [Правила для агентов](AGENTS.md), [история изменений](CHANGE_HISTORY.md).

## Чистый запуск

Команды ниже предназначены для Bash, Linux и WSL. Клонируйте репозиторий и перейдите в его корень:

```bash
git clone https://github.com/kr1speer/plant-care-rag.git
cd plant-care-rag
```

Используйте опубликованную ветку или SHA сдачи с `.env.example` и `docker-compose.yaml`; статус версии указан в [приёмке](spec/product/kt1.md). Локальные неопубликованные коммиты не попадают в свежий клон автоматически.

Выберите **один** способ: оба занимают порт 8000. В свежем клоне создайте `.env` по инструкции ниже; существующий локальный `.env` не перезаписывайте.

### Вариант 1: uv

Нужен установленный [uv](https://docs.astral.sh/uv/getting-started/installation/). Он подготовит Python 3.13, окружение и зависимости; при первой установке нужен доступ к сети.

```bash
cp .env.example .env
uv run python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Вставьте сгенерированное значение после `DJANGO_SECRET_KEY=` в `.env`, затем:

```bash
uv run python manage.py runserver
```

Откройте **http://localhost:8000/**. Остановка: Ctrl+C.

### Вариант 2: Docker Compose

Нужны работающий Docker и Compose. В WSL включите интеграцию дистрибуции в Docker Desktop. Локальные Python, uv и Node.js для этого варианта не нужны.

```bash
cp .env.example .env
docker run --rm python:3.13-slim python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Вставьте сгенерированное значение после `DJANGO_SECRET_KEY=` в `.env`, затем:

```bash
docker compose up --build
```

Откройте **http://localhost:8000/**. При первой сборке нужен доступ к образам и зависимостям. Остановка: Ctrl+C; удаление контейнера и сети проекта:

```bash
docker compose down
```

### Конфигурация

`DJANGO_SECRET_KEY` обязателен: пустое значение останавливает запуск. `.env` исключён из Git и контекста Docker. Значения среды процесса имеют приоритет над `.env`. При полной настройке через среду сам файл не обязателен.

`DJANGO_DEBUG` принимает `true`/`false`, по умолчанию `false`; для локального интерфейса и static оставьте `true`, как в шаблоне. `DJANGO_ALLOWED_HOSTS` — список через запятую, по умолчанию `localhost,127.0.0.1,[::1]`. Это конфигурация локальной разработки с runserver; контейнер публикует порт только на loopback.

### Настройка LLM

Для ответов по корпусу задайте в локальном `.env` или в окружении `LLM_API_KEY` (ключ), `LLM_MODEL` (ID модели) и `LLM_BASE_URL` (базовый URL совместимого API с префиксом версии, например `https://provider.example/v1`). Используйте один из способов запуска выше. Модель должна поддерживать Chat Completions и выдавать JSON по инструкции. Настройки передаются Compose при запуске. Ключ хранится локально. Страница и тесты запускаются без ключа, но запрос с результатами BM25 требует настроенного провайдера.

## Поиск BM25 и benchmark (КТ №2)

`app.rag.retrieve(question, k=3)` возвращает до трёх документов с лучшим фрагментом, разделом, ссылкой и баллом. Индекс — собственный код без `rank_bm25`; устройство, формат вопросов и последние метрики — в [rag.md](spec/tech/rag.md).

```bash
uv run python benchmark/run.py
uv run python benchmark/run.py --retrieval-only
uv run python benchmark/run.py --score benchmark/results/<файл>.json
```

Для полного прогона задайте настройки LLM и проверьте `mode: full` в сохранённом JSON. Если пробный вызов завершился ошибкой, runner предупреждает и переключается в `retrieval-only`.

Результаты сохраняются в `benchmark/results/<дата>.json`; поле `verdict` размечается вручную, `--score` пересчитывает метрики.

## Проверки и CI

Для разработки установите Python-зависимости и инструменты Node.js 24, затем выполните основные проверки:

```bash
uv sync --locked
npm ci
uv run python manage.py check
uv run python manage.py test tests
uv run coverage run manage.py test tests
uv run coverage report
npm run lint
npm run format:check
```

Покрытие всего `app/` со строками и ветвями должно быть **не ниже 75%**, без верхнего ограничения. Команды Ruff, djLint и исправляющего форматирования приведены в [AGENTS.md](AGENTS.md) и [инструкции качества](spec/tech/quality.md).

Браузерные тесты используют локальную HTTP-заглушку LLM. Для uv запустите `uv run python tests/browser/llm_stub.py` в отдельном терминале. Запустите Django с `LLM_API_KEY=browser-test LLM_MODEL=browser-test LLM_BASE_URL=http://127.0.0.1:8001/v1`. Для Compose передайте эти же переменные при запуске и запустите заглушку внутри контейнера командой `docker compose exec -d web uv run --no-sync python tests/browser/llm_stub.py`. Затем выполните:

```bash
npx --no-install playwright install --with-deps chromium
npm run test:browser
```

Установка системных библиотек Chromium может требовать прав администратора. `BASE_URL` меняет адрес сервера; по умолчанию `http://127.0.0.1:8000`. Отчёты сохраняются в `playwright-report/` и `test-results/`; просмотр — `npx --no-install playwright show-report`.

GitHub Actions проверяет PR в `main`, push в `main` и ручные запуски: стиль, форматирование, Django, покрытие, сборку образа и браузер против контейнера. Использует временный ключ задания, сохраняет отчёты и удаляет тестовые контейнеры. Образ и сайт не публикуются. Badge показывает реальный статус `main`; до публикации workflow и первого запуска статус может быть недоступен. Локальные результаты — в [приёмке](spec/product/kt1.md).

## Лицензии

Программа распространяется по **GNU GPL v3 или более поздней версии** — см. [LICENSE](LICENSE). Статьи [корпуса](data/corpus/) имеют отдельную лицензию **CC BY-SA 4.0**; источники, версии и атрибуция указаны в каждом файле. Зависимости распространяются по собственным лицензиям.
