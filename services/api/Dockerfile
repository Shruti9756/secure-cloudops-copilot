# syntax=docker/dockerfile:1.7

FROM python:3.14.8-alpine3.24

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install current stable Alpine updates and the C++ runtime.
# No compiler toolchain or glibc compatibility layer is installed.
RUN apk upgrade --no-cache \
    && apk add --no-cache libstdc++ \
    && addgroup -S app \
    && adduser -S -D -H -G app app

COPY pyproject.toml uv.lock ./

# Keep locked dependencies and require compatible prebuilt wheels.
# Do not download a different Python or compile dependencies from source.
RUN uv sync \
    --locked \
    --no-dev \
    --no-install-project \
    --python /usr/local/bin/python \
    --no-python-downloads \
    --no-build \
    --no-cache

# uv installs dependencies; pip and its bootstrap archive are unnecessary.
RUN /usr/local/bin/python -m pip uninstall --yes pip \
    && test -f /usr/local/lib/python3.14/ensurepip/_bundled/pip-26.2.1-py3-none-any.whl \
    && rm -- /usr/local/lib/python3.14/ensurepip/_bundled/pip-26.2.1-py3-none-any.whl

COPY --chown=app:app app ./app
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app migrations ./migrations

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()" || exit 1

CMD ["fastapi", "run", "--entrypoint", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]