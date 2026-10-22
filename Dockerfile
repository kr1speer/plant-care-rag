FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.3 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

WORKDIR /project
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY manage.py ./
COPY app ./app
COPY tests ./tests
COPY data/corpus ./data/corpus

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
