from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from quantos_cli import main
from quantos_intelligence import cli as intelligence_cli
from quantos_intelligence.collector import (
    ObservationHistory,
    PublicIntelligenceCollector,
    RawFactor,
)
from quantos_intelligence.errors import IntelligenceValidationError

AS_OF = datetime(2026, 8, 1, 12, tzinfo=UTC)
TIMESTAMP_MS = int(AS_OF.timestamp() * 1000)


def client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("get_volatility_index_data"):
        return response(request, {"result": {"data": [[TIMESTAMP_MS, 50, 60, 40, 55]]}})
    if path.endswith("get_book_summary_by_currency"):
        return response(
            request,
            {
                "result": [
                    {"instrument_name": "BTC-1AUG26-100000-P", "open_interest": 120},
                    {"instrument_name": "BTC-1AUG26-100000-C", "open_interest": 100},
                ]
            },
        )
    if path.endswith("fundingRate"):
        return response(request, [{"fundingRate": "0.0001", "fundingTime": TIMESTAMP_MS}])
    if path.endswith("klines"):
        rows = []
        for index in range(8):
            rows.append(
                [
                    TIMESTAMP_MS - (7 - index) * 86_400_000,
                    "100",
                    "110",
                    "90",
                    str(100 + index),
                    "10",
                    TIMESTAMP_MS - (7 - index) * 86_400_000,
                    str(1_000 + index * 10),
                ]
            )
        return response(request, rows)
    if path.endswith("takerlongshortRatio"):
        return response(request, [{"buySellRatio": "1.2", "timestamp": TIMESTAMP_MS}])
    if path.endswith("ticker/24hr"):
        return response(
            request,
            [
                {"symbol": symbol, "priceChangePercent": "1" if index < 6 else "-1"}
                for index, symbol in enumerate(
                    [
                        "BTCUSDT",
                        "ETHUSDT",
                        "BNBUSDT",
                        "SOLUSDT",
                        "XRPUSDT",
                        "ADAUSDT",
                        "DOGEUSDT",
                        "AVAXUSDT",
                        "LINKUSDT",
                        "DOTUSDT",
                    ]
                )
            ],
        )
    if path.endswith("VIX_History.csv"):
        return httpx.Response(
            200,
            text="DATE,OPEN,HIGH,LOW,CLOSE\n07/30/2026,17,19,16,18\n07/31/2026,18,20,17,18.2\n",
            request=request,
        )
    if path.endswith("outboundfeeds/rss"):
        return httpx.Response(
            200,
            text="""<?xml version="1.0"?><rss><channel><item>
              <title>Bitcoin gains as adoption outlook improves</title>
              <link>https://www.coindesk.com/markets/2026/08/01/bitcoin-gains</link>
              <pubDate>Sat, 01 Aug 2026 10:00:00 GMT</pubDate>
            </item></channel></rss>""",
            request=request,
        )
    return httpx.Response(404, request=request)


def response(request: httpx.Request, value) -> httpx.Response:
    return httpx.Response(200, json=value, request=request)


def test_collects_bounded_public_factors_and_headline_metadata(tmp_path: Path) -> None:
    with client() as http:
        daily = PublicIntelligenceCollector(
            http,
            ObservationHistory(tmp_path / "history"),
        ).collect(as_of=AS_OF, previous_score=42.0)

    assert daily.status == "partial"
    assert len(daily.factors) == 7
    assert all(factor.percentile == 0.5 for factor in daily.factors)
    values = {factor.key: factor.raw_value for factor in daily.factors}
    assert values["crypto_volatility"] == 55
    assert values["options_positioning"] == 1.2
    assert values["liquidation_balance"] == pytest.approx(0.2)
    assert values["market_breadth"] == 0.6
    assert values["macro_risk"] == 18.2
    assert daily.news[0].assets == ("BTC",)
    assert daily.news[0].sentiment > 0
    assert "original article" in daily.news[0].summary


def test_marks_input_complete_after_thirty_daily_observations(tmp_path: Path) -> None:
    history = ObservationHistory(tmp_path / "history")
    keys = (
        "crypto_volatility",
        "options_positioning",
        "perpetual_positioning",
        "momentum_volume",
        "liquidation_balance",
        "market_breadth",
        "macro_risk",
    )
    for days_ago in range(29, 0, -1):
        observed = AS_OF - timedelta(days=days_ago)
        history.record(
            tuple(
                RawFactor(
                    key,
                    float(index + days_ago),
                    "fixture",
                    "https://example.com",
                    observed,
                )
                for index, key in enumerate(keys)
            ),
            observed.date().isoformat(),
        )

    with client() as http:
        daily = PublicIntelligenceCollector(http, history).collect(as_of=AS_OF)

    assert daily.status == "complete"
    assert all(0 <= factor.percentile <= 1 for factor in daily.factors)
    assert any(factor.percentile != 0.5 for factor in daily.factors)


def test_history_atomically_pins_the_first_complete_daily_batch(tmp_path: Path) -> None:
    history = ObservationHistory(tmp_path)
    keys = (
        "crypto_volatility",
        "options_positioning",
        "perpetual_positioning",
        "momentum_volume",
        "liquidation_balance",
        "market_breadth",
        "macro_risk",
    )
    factors = tuple(
        RawFactor(key, float(index), "fixture", "https://example.com", AS_OF)
        for index, key in enumerate(keys)
    )
    first = history.record(factors, "2026-08-01")
    moved = tuple(
        RawFactor(
            factor.key,
            factor.value + 100,
            "changed",
            "https://changed.example.com",
            factor.observed_at + timedelta(hours=1),
        )
        for factor in factors
    )
    second = history.record(moved, "2026-08-01")

    assert first[0] == second[0] == dict.fromkeys(keys, 0.5)
    assert first[1] is second[1] is False
    assert first[2] == second[2]
    assert {factor.value for factor in second[2]} == {float(index) for index in range(7)}
    assert {factor.unit for factor in second[2]} == {"fixture"}
    assert {factor.observed_at for factor in second[2]} == {AS_OF}


def test_rejects_naive_as_of_and_incomplete_history_batch(tmp_path: Path) -> None:
    with client() as http:
        collector = PublicIntelligenceCollector(http, ObservationHistory(tmp_path))
        with pytest.raises(IntelligenceValidationError, match="timezone"):
            collector.collect(as_of=datetime(2026, 8, 1, 12))

    with pytest.raises(IntelligenceValidationError, match="every factor"):
        ObservationHistory(tmp_path).record(
            (RawFactor("macro_risk", 18.2, "VIX", "https://example.com", AS_OF),),
            "2026-08-01",
        )


def test_cli_collects_then_builds_current_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(intelligence_cli, "build_public_client", client)
    current = tmp_path / "inputs" / "current.json"
    history = tmp_path / "history"
    published = tmp_path / "published"

    assert (
        main(
            [
                "intelligence",
                "collect",
                "--output",
                str(current),
                "--history-root",
                str(history),
                "--as-of",
                "2026-08-01T12:00:00Z",
            ]
        )
        == 0
    )
    collected = json.loads(capsys.readouterr().out)
    assert collected["factor_count"] == 7
    assert collected["status"] == "partial"
    assert json.loads(current.read_text(encoding="utf-8"))["date"] == "2026-08-01"

    assert (
        main(
            [
                "intelligence",
                "build",
                "--input",
                str(current),
                "--output-root",
                str(published),
            ]
        )
        == 0
    )
    built = json.loads(capsys.readouterr().out)
    assert built["date"] == "2026-08-01"
    assert Path(built["latest"]).read_bytes() == Path(built["snapshot"]).read_bytes()
