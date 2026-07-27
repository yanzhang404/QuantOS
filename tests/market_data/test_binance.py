from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from quantos_market_data.binance import MAX_PAGE_SIZE, BinanceSpotClient
from quantos_market_data.errors import ConfigurationError, DownloadError
from quantos_market_data.models import Interval


def binance_row(open_ms: int, interval_ms: int) -> list[Any]:
    return [
        open_ms,
        "100",
        "110",
        "90",
        "105",
        "12.5",
        open_ms + interval_ms - 1,
        "1280",
        42,
        "6",
        "640",
        "0",
    ]


def test_paginates_half_open_time_range(start_time: datetime) -> None:
    interval = Interval.ONE_HOUR
    start_ms = int(start_time.timestamp() * 1_000)
    pages = [
        [
            binance_row(start_ms + index * interval.milliseconds, interval.milliseconds)
            for index in range(MAX_PAGE_SIZE)
        ],
        [
            binance_row(
                start_ms + (MAX_PAGE_SIZE + index) * interval.milliseconds,
                interval.milliseconds,
            )
            for index in range(2)
        ],
    ]
    requested_starts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_starts.append(int(request.url.params["startTime"]))
        return httpx.Response(200, json=pages[len(requested_starts) - 1])

    http_client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    client = BinanceSpotClient(client=http_client)
    end = start_time + timedelta(hours=MAX_PAGE_SIZE + 2)

    result = client.fetch_klines(
        symbol="btcusdt",
        interval=interval,
        start=start_time,
        end=end,
    )

    assert len(result) == MAX_PAGE_SIZE + 2
    assert requested_starts == [
        start_ms,
        start_ms + MAX_PAGE_SIZE * interval.milliseconds,
    ]
    assert result[-1].open_time == end - timedelta(hours=1)


def test_retries_transient_status_and_honors_retry_after(start_time: datetime) -> None:
    attempts = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, text="slow down")
        start_ms = int(start_time.timestamp() * 1_000)
        return httpx.Response(
            200,
            json=[binance_row(start_ms, Interval.ONE_HOUR.milliseconds)],
        )

    http_client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    client = BinanceSpotClient(
        client=http_client,
        max_retries=1,
        sleep=delays.append,
    )

    result = client.fetch_klines(
        symbol="BTCUSDT",
        interval=Interval.ONE_HOUR,
        start=start_time,
        end=start_time + timedelta(hours=1),
    )

    assert len(result) == 1
    assert attempts == 2
    assert delays == [2.0]


def test_reports_non_retryable_exchange_error(start_time: datetime) -> None:
    http_client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol"})
        ),
    )
    client = BinanceSpotClient(client=http_client)

    with pytest.raises(DownloadError, match="HTTP 400"):
        client.fetch_klines(
            symbol="BTCUSDT",
            interval=Interval.ONE_HOUR,
            start=start_time,
            end=start_time + timedelta(hours=1),
        )


def test_rejects_unaligned_range(start_time: datetime) -> None:
    http_client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    client = BinanceSpotClient(client=http_client)

    with pytest.raises(ConfigurationError, match="align"):
        client.fetch_klines(
            symbol="BTCUSDT",
            interval=Interval.ONE_HOUR,
            start=start_time + timedelta(minutes=1),
            end=start_time + timedelta(hours=1),
        )


def test_reports_network_failure_after_bounded_retries(start_time: datetime) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("offline", request=request)

    client = BinanceSpotClient(
        client=httpx.Client(
            base_url="https://example.test",
            transport=httpx.MockTransport(handler),
        ),
        max_retries=1,
        backoff_seconds=0,
        sleep=lambda _: None,
    )

    with pytest.raises(DownloadError, match="request failed"):
        client.fetch_klines(
            symbol="BTCUSDT",
            interval=Interval.ONE_HOUR,
            start=start_time,
            end=start_time + timedelta(hours=1),
        )
    assert attempts == 2


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, text="not-json"), "invalid JSON"),
        (httpx.Response(200, json={"rows": []}), "list of rows"),
    ],
)
def test_rejects_invalid_exchange_payload(
    response: httpx.Response,
    message: str,
    start_time: datetime,
) -> None:
    client = BinanceSpotClient(
        client=httpx.Client(
            base_url="https://example.test",
            transport=httpx.MockTransport(lambda _: response),
        )
    )

    with pytest.raises(DownloadError, match=message):
        client.fetch_klines(
            symbol="BTCUSDT",
            interval=Interval.ONE_HOUR,
            start=start_time,
            end=start_time + timedelta(hours=1),
        )
