FROM python:3.12.11-slim-bookworm

WORKDIR /app

COPY services/market-data /tmp/market-data
RUN python -m pip install --no-cache-dir /tmp/market-data \
    && useradd --create-home --uid 10001 quantos \
    && mkdir -p /app/data \
    && chown -R quantos:quantos /app

USER quantos

ENTRYPOINT ["quantos-us-radar"]
CMD ["live", "--feed", "sip"]
