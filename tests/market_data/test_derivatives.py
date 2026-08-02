from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from quantos_market_data import derivatives
from quantos_market_data.derivatives import (
    BinanceFuturesPublicClient,
    DerivativeDatasetStore,
    FundingRateObservation,
    OpenInterestObservation,
)
from quantos_market_data.errors import ConfigurationError, DatasetError, DownloadError
from quantos_market_data.models import Interval

START = datetime(2026, 7, 30, tzinfo=UTC)
END = datetime(2026, 8, 2, tzinfo=UTC)


def mock_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("fundingRate"):
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "BTCUSDT",
                        "fundingTime": int((START + timedelta(hours=8)).timestamp() * 1000),
                        "fundingRate": "0.0001",
                        "markPrice": "115000.5",
                        "rateType": "Regular",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "fundingTime": int((START + timedelta(hours=16)).timestamp() * 1000),
                        "fundingRate": "-0.0002",
                        "markPrice": "114000",
                        "rateType": "Regular",
                    },
                ],
                request=request,
            )
        if request.url.path.endswith("openInterestHist"):
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "BTCUSDT",
                        "sumOpenInterest": "1000.25",
                        "sumOpenInterestValue": "115000000.5",
                        "timestamp": int((START + timedelta(hours=4)).timestamp() * 1000),
                    },
                    {
                        "symbol": "BTCUSDT",
                        "sumOpenInterest": "1010.5",
                        "sumOpenInterestValue": "116000000",
                        "timestamp": int((START + timedelta(hours=8)).timestamp() * 1000),
                    },
                ],
                request=request,
            )
        return httpx.Response(404, request=request)

    return httpx.Client(
        base_url="https://fapi.binance.com",
        transport=httpx.MockTransport(handler),
    )


def test_downloads_public_funding_and_open_interest_without_credentials() -> None:
    http = mock_client()
    client = BinanceFuturesPublicClient(client=http)

    funding = client.fetch_funding(symbol="btcusdt", start=START, end=END)
    interest = client.fetch_open_interest(
        symbol="BTCUSDT", period=Interval.FOUR_HOURS, start=START, end=END
    )

    assert [item.funding_rate for item in funding] == [Decimal("0.0001"), Decimal("-0.0002")]
    assert interest[-1].open_interest_value == Decimal("116000000")


def test_rejects_non_allowlisted_futures_host() -> None:
    with pytest.raises(ConfigurationError, match="allow-listed"):
        BinanceFuturesPublicClient(base_url="https://example.com")
    with pytest.raises(ConfigurationError, match="allow-listed"):
        BinanceFuturesPublicClient(base_url="https://fapi.binance.com:8443")


def test_publishes_separate_content_addressed_derivatives_datasets(tmp_path: Path) -> None:
    client = BinanceFuturesPublicClient(client=mock_client())
    funding = client.fetch_funding(symbol="BTCUSDT", start=START, end=END)
    interest = client.fetch_open_interest(
        symbol="BTCUSDT", period=Interval.FOUR_HOURS, start=START, end=END
    )
    store = DerivativeDatasetStore(
        tmp_path,
        now=lambda: datetime(2026, 8, 2, 1, tzinfo=UTC),
    )

    funding_path, funding_manifest = store.publish_funding(
        funding, requested_start=START, requested_end=END
    )
    interest_path, interest_manifest = store.publish_open_interest(
        interest, requested_start=START, requested_end=END
    )

    assert funding_path != interest_path
    assert funding_manifest.series == "funding-rate"
    assert funding_manifest.source_limit is None
    assert interest_manifest.series == "open-interest"
    assert interest_manifest.period == "4h"
    assert interest_manifest.source_limit == "latest 1 month"
    assert store.verify(funding_path) == funding_manifest
    assert store.verify(interest_path) == interest_manifest


def test_download_services_publish_typed_datasets(monkeypatch, tmp_path: Path) -> None:
    funding = FundingRateObservation(
        "BTCUSDT", START + timedelta(hours=8), Decimal("0.0001"), Decimal("1"), "Regular"
    )
    interest = OpenInterestObservation(
        "BTCUSDT", Interval.FOUR_HOURS, START + timedelta(hours=4), Decimal("10"), Decimal("20")
    )

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def fetch_funding(self, **_):
            return [funding]

        def fetch_open_interest(self, **_):
            return [interest]

    monkeypatch.setattr(derivatives, "BinanceFuturesPublicClient", FakeClient)
    funding_result = derivatives.download_funding_dataset(
        symbol="BTCUSDT",
        start=START,
        end=END,
        data_root=tmp_path,
        now=END,
    )
    interest_result = derivatives.download_open_interest_dataset(
        symbol="BTCUSDT",
        period=Interval.FOUR_HOURS,
        start=START,
        end=END,
        data_root=tmp_path,
        now=END,
    )

    assert funding_result.manifest.series == "funding-rate"
    assert interest_result.manifest.series == "open-interest"


def test_rejects_long_oi_windows_and_tampered_datasets(tmp_path: Path) -> None:
    client = BinanceFuturesPublicClient(client=mock_client())
    with pytest.raises(ConfigurationError, match="1-month"):
        client.fetch_open_interest(
            symbol="BTCUSDT",
            period=Interval.FOUR_HOURS,
            start=START - timedelta(days=40),
            end=END,
        )

    funding = client.fetch_funding(symbol="BTCUSDT", start=START, end=END)
    store = DerivativeDatasetStore(tmp_path)
    path, _ = store.publish_funding(funding, requested_start=START, requested_end=END)
    (path / "manifest.json").write_text(json.dumps({"schema_version": "wrong"}))
    with pytest.raises(DatasetError, match="manifest"):
        store.verify(path)


def test_recomputes_content_hash_from_parquet(tmp_path: Path) -> None:
    client = BinanceFuturesPublicClient(client=mock_client())
    funding = client.fetch_funding(symbol="BTCUSDT", start=START, end=END)
    store = DerivativeDatasetStore(tmp_path)
    path, _ = store.publish_funding(funding, requested_start=START, requested_end=END)
    parquet = path / "part-00000.parquet"
    table = pq.read_table(parquet)
    records = table.to_pylist()
    records[0]["funding_rate"] = Decimal("0.5")
    pq.write_table(pa.Table.from_pylist(records, schema=table.schema), parquet, compression="zstd")

    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["file_sha256"] = hashlib.sha256(parquet.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(DatasetError, match="verification failed"):
        store.verify(path)


def test_rejects_duplicate_derivatives_observations(tmp_path: Path) -> None:
    row = FundingRateObservation(
        "BTCUSDT", START + timedelta(hours=8), Decimal("0.0001"), Decimal("1"), "Regular"
    )
    with pytest.raises(DatasetError, match="ordered, and unique"):
        DerivativeDatasetStore(tmp_path).publish_funding(
            [row, row], requested_start=START, requested_end=END
        )

    invalid = OpenInterestObservation(
        "BTCUSDT", Interval.FOUR_HOURS, START, Decimal("-1"), Decimal("10")
    )
    with pytest.raises(DownloadError, match="invalid open-interest"):
        DerivativeDatasetStore(tmp_path).publish_open_interest(
            [invalid], requested_start=START, requested_end=END
        )
