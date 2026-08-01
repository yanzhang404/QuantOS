# syntax=docker/dockerfile:1.7

FROM golang:1.26.4-bookworm AS api-builder

WORKDIR /src
COPY go.mod ./
COPY apps/api ./apps/api
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" \
    -o /out/quantos-api ./apps/api/cmd/quantos-api

FROM ghcr.io/astral-sh/uv:0.9.14 AS uv

FROM python:3.12.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_FROZEN=1 \
    UV_NO_SYNC=1 \
    QUANTOS_LISTEN=0.0.0.0:8080 \
    QUANTOS_DATA_ROOT=/var/lib/quantos/data \
    QUANTOS_ARTIFACT_ROOT=/var/lib/quantos/artifacts/experiments \
    QUANTOS_STATE_ROOT=/var/lib/quantos/tasks \
    QUANTOS_INTELLIGENCE_ROOT=/var/lib/quantos/intelligence

WORKDIR /app
COPY --from=uv /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock README.md ./
COPY apps/worker ./apps/worker
COPY packages ./packages
COPY services ./services
RUN uv sync --frozen --no-dev

COPY --from=api-builder /out/quantos-api /usr/local/bin/quantos-api

RUN useradd --create-home --uid 10001 quantos \
    && mkdir -p \
        /var/lib/quantos/data \
        /var/lib/quantos/artifacts/experiments \
        /var/lib/quantos/tasks \
        /var/lib/quantos/intelligence \
    && chown -R quantos:quantos /var/lib/quantos

USER quantos
VOLUME ["/var/lib/quantos"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"]

ENTRYPOINT ["quantos-api"]
