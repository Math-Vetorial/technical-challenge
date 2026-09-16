FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY . .

RUN uv sync

CMD ["sh", "-c", "uv run python -m data_foundry run --limit ${RUN_LIMIT:-12}"]
