"""Read-only Binance Spot REST adapter."""

from __future__ import annotations

import email.utils
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx

from .errors import ConfigurationError, DownloadError
from .models import (
    Interval,
    Kline,
    datetime_to_milliseconds,
    normalize_symbol,
)

DEFAULT_BASE_URL = "https://data-api.binance.vision"
MAX_PAGE_SIZE = 1_000
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class BinanceSpotClient:
    """Minimal public-market-data client with bounded retries and pagination."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_retries < 0:
            raise ConfigurationError("max_retries must be non-negative")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"User-Agent": "QuantOS-MarketData/0.1"},
        )
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep

    def __enter__(self) -> BinanceSpotClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_klines(
        self,
        *,
        symbol: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[Kline]:
        """Fetch closed Klines in the half-open interval ``[start, end)``."""

        normalized_symbol = normalize_symbol(symbol)
        start_ms = datetime_to_milliseconds(start)
        end_ms = datetime_to_milliseconds(end)
        if start_ms >= end_ms:
            raise ConfigurationError("start must be earlier than end")
        if start_ms % interval.milliseconds:
            raise ConfigurationError(f"start must align to a UTC {interval.value} boundary")
        if end_ms % interval.milliseconds:
            raise ConfigurationError(f"end must align to a UTC {interval.value} boundary")

        cursor = start_ms
        result: list[Kline] = []
        seen_open_times: set[int] = set()

        while cursor < end_ms:
            rows = self._request_page(
                {
                    "symbol": normalized_symbol,
                    "interval": interval.value,
                    "startTime": cursor,
                    "endTime": end_ms - 1,
                    "limit": MAX_PAGE_SIZE,
                }
            )
            if not rows:
                break

            last_open_ms: int | None = None
            for raw_row in rows:
                kline = Kline.from_binance_row(normalized_symbol, interval, raw_row)
                open_ms = datetime_to_milliseconds(kline.open_time)
                last_open_ms = open_ms
                if open_ms < start_ms or open_ms >= end_ms:
                    continue
                if open_ms not in seen_open_times:
                    result.append(kline)
                    seen_open_times.add(open_ms)

            if last_open_ms is None:
                break
            next_cursor = last_open_ms + interval.milliseconds
            if next_cursor <= cursor:
                raise DownloadError("Binance pagination did not advance")
            cursor = next_cursor
            if len(rows) < MAX_PAGE_SIZE:
                break

        return result

    def _request_page(self, params: dict[str, str | int]) -> list[list[Any]]:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.get("/api/v3/klines", params=params)
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    raise DownloadError(f"Binance request failed: {exc}") from exc
                self._sleep(self._backoff_seconds * (2**attempt))
                continue

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                self._sleep(self._retry_delay(response, attempt))
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text[:300]
                raise DownloadError(
                    f"Binance returned HTTP {response.status_code}: {detail}"
                ) from exc

            try:
                payload = response.json()
            except ValueError as exc:
                raise DownloadError("Binance returned invalid JSON") from exc
            if not isinstance(payload, list) or any(not isinstance(row, list) for row in payload):
                raise DownloadError("Binance Kline response must be a list of rows")
            return payload

        raise AssertionError("retry loop must return or raise")

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            if retry_after.isdigit():
                return max(0.0, float(retry_after))
            try:
                parsed = email.utils.parsedate_to_datetime(retry_after)
                return max(0.0, parsed.timestamp() - time.time())
            except (TypeError, ValueError, OverflowError):
                pass
        return self._backoff_seconds * (2**attempt)
