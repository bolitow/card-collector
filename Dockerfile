# Une seule image pour l'API, le worker et les migrations (docs/architecture.md, section 2).

FROM node:22-slim AS web
WORKDIR /src/web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY shared /src/shared
COPY web ./
RUN pnpm build

FROM python:3.13-slim AS app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend ./
COPY --from=web /src/web/dist /srv/web/dist
RUN useradd --system --uid 1001 app && mkdir -p /srv/backend/var && chown -R app /srv/backend/var
USER app
ENV PATH="/srv/backend/.venv/bin:$PATH"
EXPOSE 8000
# Par défaut : l'API. Le worker lance `python -m app.worker`, les migrations `alembic upgrade head`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
