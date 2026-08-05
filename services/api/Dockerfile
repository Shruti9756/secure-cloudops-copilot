# syntax=docker/dockerfile:1.7

FROM python:3.14-slim

# Copy a pinned uv binary into the image.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Do not run the API as root.
RUN addgroup --system app && adduser --system --ingroup app app

# Copy dependency files first so Docker can cache dependency installation.
COPY pyproject.toml uv.lock ./

# Install only locked production dependencies, excluding test and lint tools.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Copy only application source after dependencies are installed.
COPY --chown=app:app app ./app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()" || exit 1

CMD ["fastapi", "run", "--entrypoint", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]