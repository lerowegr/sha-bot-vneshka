# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS frontend
WORKDIR /build

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY index.html tsconfig.json vite.config.ts ./
COPY public ./public
COPY src ./src

# This URL is public frontend configuration, not a secret.
ARG VITE_TELEGRAM_CHANNEL_URL=
ENV VITE_TELEGRAM_CHANNEL_URL=${VITE_TELEGRAM_CHANNEL_URL}
RUN npm run build


FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HTTP_HOST=0.0.0.0 \
    HTTP_PORT=8080 \
    QUIZ_DB_PATH=/app/data/quiz.sqlite3

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

COPY bot ./bot
COPY database ./database
COPY web ./web
COPY --from=frontend /build/dist ./dist

RUN mkdir -p /app/data && chown -R app:app /app
USER app

EXPOSE 8080
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3).read()"]

CMD ["python", "-m", "bot"]
