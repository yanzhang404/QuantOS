from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from quantos_market_data import cli, service
from quantos_market_data.bundle import PRODUCT_INTERVALS, PRODUCT_SYMBOLS
from quantos_market_data.errors import ConfigurationError
from quantos_market_data.models import Interval
from quantos_market_data.storage import DatasetStore

from .conftest import make_kline


def test_download_service_orchestrates_public_data_publish(
    monkeypatch,
    tmp_path,
    start_time,
) -> None:
    klines = [make_kline(start_time + timedelta(hours=index)) for index in range(2)]
    observed: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, base_url: str) -> None:
            observed["base_url"] = base_url

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def fetch_klines(self, **kwargs):
            observed.update(kwargs)
            return klines

    monkeypatch.setattr(service, "BinanceSpotClient", FakeClient)

    result = service.download_dataset(
        symbol="BTCUSDT",
        interval=Interval.ONE_HOUR,
        start=start_time,
        end=start_time + timedelta(hours=2),
        data_root=tmp_path,
        base_url="https://example.test",
        now=start_time + timedelta(days=1),
    )

    assert result.manifest.row_count == 2
    assert result.manifest.source == "https://example.test/api/v3/klines"
    assert observed["symbol"] == "BTCUSDT"


def test_download_service_rejects_incomplete_interval(tmp_path, start_time) -> None:
    with pytest.raises(ConfigurationError, match="latest closed"):
        service.download_dataset(
            symbol="BTCUSDT",
            interval=Interval.ONE_HOUR,
            start=start_time,
            end=start_time + timedelta(hours=3),
            data_root=tmp_path,
            now=start_time + timedelta(hours=2, minutes=30),
        )


def test_sync_product_matrix_downloads_every_member(monkeypatch, tmp_path, start_time) -> None:
    calls: list[tuple[str, Interval]] = []

    def fake_download_dataset(**kwargs):
        symbol = kwargs["symbol"]
        interval = kwargs["interval"]
        calls.append((symbol, interval))
        rows = int(timedelta(days=1).total_seconds() * 1_000 / interval.milliseconds)
        return DatasetStore(tmp_path).publish(
            [
                make_kline(
                    start_time + timedelta(milliseconds=interval.milliseconds * index),
                    symbol=symbol,
                    interval=interval,
                )
                for index in range(rows)
            ],
            requested_start=start_time,
            requested_end=start_time + timedelta(days=1),
            source="https://example.test/api/v3/klines",
        )

    monkeypatch.setattr(service, "download_dataset", fake_download_dataset)
    bundle = service.sync_product_matrix(
        start=start_time,
        end=start_time + timedelta(days=1),
        data_root=tmp_path,
        base_url="https://example.test",
        now=start_time + timedelta(days=2),
    )

    assert calls == [
        (symbol, interval) for symbol in PRODUCT_SYMBOLS for interval in PRODUCT_INTERVALS
    ]
    assert len(bundle.manifest.members) == 10


def test_extend_dataset_downloads_only_missing_tail(monkeypatch, tmp_path, start_time) -> None:
    source = DatasetStore(tmp_path).publish(
        [make_kline(start_time), make_kline(start_time + timedelta(hours=1))],
        requested_start=start_time,
        requested_end=start_time + timedelta(hours=2),
        source="https://example.test/api/v3/klines",
    )
    observed: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, base_url: str) -> None:
            observed["base_url"] = base_url

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def fetch_klines(self, **kwargs):
            observed.update(kwargs)
            return [make_kline(start_time + timedelta(hours=2))]

    monkeypatch.setattr(service, "BinanceSpotClient", FakeClient)
    refreshed = service.extend_dataset(
        dataset=source.path,
        end=start_time + timedelta(hours=3),
        data_root=tmp_path,
        base_url="https://example.test",
        now=start_time + timedelta(days=1),
    )

    assert observed["start"] == start_time + timedelta(hours=2)
    assert refreshed.path != source.path
    assert refreshed.manifest.row_count == 3
    assert source.manifest.row_count == 2


def test_extend_dataset_is_noop_at_existing_boundary(monkeypatch, tmp_path, start_time) -> None:
    source = DatasetStore(tmp_path).publish(
        [make_kline(start_time)],
        requested_start=start_time,
        requested_end=start_time + timedelta(hours=1),
        source="https://example.test/api/v3/klines",
    )
    monkeypatch.setattr(
        service,
        "BinanceSpotClient",
        lambda **_: pytest.fail("no network call expected"),
    )

    refreshed = service.extend_dataset(
        dataset=source.path,
        end=start_time + timedelta(hours=1),
        data_root=tmp_path,
        base_url="https://example.test",
    )

    assert refreshed.path == source.path


def test_latest_closed_matrix_end_uses_utc_midnight() -> None:
    observed = datetime(2026, 8, 1, 16, 30, tzinfo=UTC)

    assert service.latest_closed_matrix_end(observed) == datetime(2026, 8, 1, tzinfo=UTC)


def test_sync_current_backfills_when_start_has_no_bundle(monkeypatch, tmp_path, start_time) -> None:
    sentinel = object()
    observed: dict[str, object] = {}

    def fake_sync(**kwargs):
        observed.update(kwargs)
        return sentinel

    monkeypatch.setattr(service, "sync_product_matrix", fake_sync)
    result = service.sync_current_product_matrix(
        start=start_time,
        data_root=tmp_path,
        now=start_time + timedelta(days=3, hours=12),
    )

    assert result is sentinel
    assert observed["end"] == start_time + timedelta(days=3)


def test_cli_download_prints_machine_readable_result(monkeypatch, capsys, tmp_path) -> None:
    published = SimpleNamespace(
        path=tmp_path / "version=abc",
        manifest=SimpleNamespace(dataset_version="abc", row_count=24),
    )
    monkeypatch.setattr(cli, "download_dataset", lambda **_: published)

    result = cli.main(
        [
            "data",
            "download",
            "--symbol",
            "BTCUSDT",
            "--interval",
            "1h",
            "--start",
            "2024-01-01T00:00:00Z",
            "--end",
            "2024-01-02T00:00:00Z",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["dataset_version"] == "abc"
    assert payload["rows"] == 24


@pytest.mark.parametrize(
    ("series", "period", "function_name"),
    [
        ("funding-rate", [], "download_funding_dataset"),
        ("open-interest", ["--period", "4h"], "download_open_interest_dataset"),
    ],
)
def test_cli_derivatives_prints_versioned_result(
    monkeypatch, capsys, tmp_path, series, period, function_name
) -> None:
    published = SimpleNamespace(
        path=tmp_path / "version=abc",
        manifest=SimpleNamespace(
            dataset_version="abc",
            series=series,
            row_count=3,
            source_limit="latest 1 month" if series == "open-interest" else None,
        ),
    )
    observed: dict[str, object] = {}

    def publish(**kwargs):
        observed.update(kwargs)
        return published

    monkeypatch.setattr(cli, function_name, publish)
    result = cli.main(
        [
            "data",
            "derivatives",
            "--series",
            series,
            "--symbol",
            "BTCUSDT",
            *period,
            "--start",
            "2026-07-30T00:00:00Z",
            "--end",
            "2026-08-01T00:00:00Z",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["dataset_version"] == "abc"
    assert payload["series"] == series
    assert observed["symbol"] == "BTCUSDT"


def test_cli_derivatives_requires_series_specific_period(capsys) -> None:
    result = cli.main(
        [
            "data",
            "derivatives",
            "--series",
            "open-interest",
            "--symbol",
            "BTCUSDT",
            "--start",
            "2026-07-30T00:00:00Z",
            "--end",
            "2026-08-01T00:00:00Z",
        ]
    )

    assert result == 2
    assert "--period is required" in capsys.readouterr().err


def test_cli_align_derivatives_prints_coverage_counts(monkeypatch, capsys, tmp_path) -> None:
    published = SimpleNamespace(
        path=tmp_path / "version=aligned",
        manifest=SimpleNamespace(
            dataset_version="aligned",
            series="funding-rate",
            row_count=4,
            matched_count=2,
            stale_count=1,
            no_prior_count=1,
        ),
    )
    observed: dict[str, object] = {}

    def publish(**kwargs):
        observed.update(kwargs)
        return published

    monkeypatch.setattr(cli, "materialize_derivatives_alignment", publish)
    result = cli.main(
        [
            "data",
            "align-derivatives",
            "--spot-dataset",
            "spot/version=abc",
            "--derivative-dataset",
            "derivatives/version=def",
            "--start",
            "2026-08-01T00:00:00Z",
            "--end",
            "2026-08-01T04:00:00Z",
            "--max-age",
            "90m",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["matched"] == 2
    assert payload["stale"] == 1
    assert observed["max_age_ms"] == 5_400_000


@pytest.mark.parametrize(
    ("value", "expected"), [("500ms", 500), ("30s", 30_000), ("15m", 900_000), ("2h", 7_200_000)]
)
def test_cli_parses_positive_durations(value: str, expected: int) -> None:
    assert cli._duration_ms(value) == expected


@pytest.mark.parametrize("value", ["0h", "-1m", "5", "hour"])
def test_cli_rejects_invalid_durations(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="duration"):
        cli._duration_ms(value)


def test_cli_sync_matrix_prints_exact_member_identities(monkeypatch, capsys, tmp_path) -> None:
    member = SimpleNamespace(symbol="BTCUSDT", interval="5m", dataset_version="abc", row_count=288)
    published = SimpleNamespace(
        path=tmp_path / "version=bundle",
        manifest=SimpleNamespace(bundle_version="bundle", members=(member,)),
    )
    monkeypatch.setattr(cli, "sync_product_matrix", lambda **_: published)

    result = cli.main(
        [
            "data",
            "sync-matrix",
            "--start",
            "2024-01-01T00:00:00Z",
            "--end",
            "2024-01-02T00:00:00Z",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["bundle_version"] == "bundle"
    assert payload["members"] == [
        {"dataset_version": "abc", "interval": "5m", "rows": 288, "symbol": "BTCUSDT"}
    ]


def test_cli_sync_current_exports_coverage(monkeypatch, capsys, tmp_path) -> None:
    manifest = SimpleNamespace(
        bundle_version="current",
        requested_start="2021-01-01T00:00:00Z",
        requested_end="2026-08-01T00:00:00Z",
        members=(SimpleNamespace(row_count=100), SimpleNamespace(row_count=50)),
    )
    published = SimpleNamespace(path=tmp_path / "version=current", manifest=manifest)
    monkeypatch.setattr(cli, "sync_current_product_matrix", lambda **_: published)
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        cli,
        "write_coverage_evidence",
        lambda value, output: observed.update(manifest=value, output=output),
    )
    output = tmp_path / "coverage.json"

    result = cli.main(
        [
            "data",
            "sync-current",
            "--start",
            "2021-01-01T00:00:00Z",
            "--coverage-output",
            str(output),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["bundle_version"] == "current"
    assert payload["rows"] == 150
    assert observed == {"manifest": manifest, "output": output}


def test_cli_validate_and_query(capsys, monkeypatch, tmp_path, start_time) -> None:
    published = DatasetStore(tmp_path).publish(
        [make_kline(start_time)],
        requested_start=start_time,
        requested_end=start_time + timedelta(hours=1),
        source="https://example.test/api/v3/klines",
    )
    assert cli.main(["data", "validate", "--dataset", str(published.path)]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["is_valid"] is True

    monkeypatch.setattr(
        cli,
        "query_klines",
        lambda *_args, **_kwargs: [
            {
                "open_time": datetime(2024, 1, 1, tzinfo=UTC),
                "close": "100.0",
            }
        ],
    )
    assert (
        cli.main(
            [
                "data",
                "query",
                "--dataset",
                str(published.path),
                "--limit",
                "1",
            ]
        )
        == 0
    )
    query = json.loads(capsys.readouterr().out)
    assert query["open_time"] == "2024-01-01T00:00:00Z"


def test_cli_reports_domain_error(monkeypatch, capsys) -> None:
    def fail(**_):
        raise ConfigurationError("bad range")

    monkeypatch.setattr(cli, "download_dataset", fail)
    result = cli.main(
        [
            "data",
            "download",
            "--symbol",
            "BTCUSDT",
            "--interval",
            "1h",
            "--start",
            "2024-01-01T00:00:00Z",
            "--end",
            "2024-01-02T00:00:00Z",
        ]
    )

    assert result == 2
    assert "bad range" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["2024-01-01T00:00:00", "not-a-date"])
def test_cli_rejects_invalid_timestamp(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="timestamp"):
        cli._datetime(value)


def test_json_value_preserves_plain_values() -> None:
    assert cli.json_value(Path("data")) == Path("data")
