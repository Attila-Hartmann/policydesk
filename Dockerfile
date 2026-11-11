# Build stage: dependencies from the frozen lockfile only, so this layer is cached until uv.lock changes.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Test stage, for running the fast test suite without uv on the host: docker build --target test .
FROM build AS test
RUN uv sync --frozen
COPY . .
RUN uv run --frozen pytest --cov

# Runtime: no uv, no dev dependencies, non-root user.
FROM python:3.12-slim
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 HOST=0.0.0.0
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app policydesk/ policydesk/
COPY --chown=app:app data/ data/
# The index is written here at startup, by the non-root user.
RUN mkdir var && chown app:app var
USER app
EXPOSE 8000
# Generous start period: on first start, ingest and the model check can take minutes on a CPU-only machine.
HEALTHCHECK --interval=10s --timeout=5s --start-period=600s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
# Ingest (skipped if the index is up to date), model check, then the API.
CMD ["python", "-m", "policydesk", "serve"]
