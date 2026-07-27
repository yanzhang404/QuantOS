from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from quantos_market_data import cli, service
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
