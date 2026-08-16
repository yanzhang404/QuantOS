import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantos_market_data.alpaca import JsonLineBarStream
from quantos_market_data.notifiers import CompositeNotifier, format_us_heat_report
from quantos_market_data.us_models import USEquityBar
from quantos_market_data.us_radar import (
    USHeatConfig, USEquityHeatEngine, USLiveRadarRunner, is_regular_session,
)


def bar(symbol, minute, close, volume, *, timestamp=None):
    timestamp = timestamp or datetime(2026, 8, 14, 13, 30 + minute, tzinfo=timezone.utc)
    return USEquityBar(
        symbol=symbol, timestamp=timestamp, open=close - 0.2,
        high=close + 0.3, low=close - 0.3, close=close,
        volume=volume, vwap=close - 0.1, trade_count=100,
    )


class USBarTests(unittest.TestCase):
    def test_regular_session_handles_summer_and_winter_offsets(self):
        self.assertTrue(is_regular_session(datetime(2026, 8, 14, 13, 30, tzinfo=timezone.utc)))
        self.assertFalse(is_regular_session(datetime(2026, 8, 14, 13, 29, tzinfo=timezone.utc)))
        self.assertTrue(is_regular_session(datetime(2026, 12, 14, 14, 30, tzinfo=timezone.utc)))

    def test_bar_rejects_invalid_range(self):
        with self.assertRaisesRegex(ValueError, "high"):
            USEquityBar(
                symbol="AAPL", timestamp=datetime.now(timezone.utc), open=10,
                high=9, low=8, close=10, volume=1, vwap=9, trade_count=1,
            )


class HeatEngineTests(unittest.TestCase):
    def test_ranks_moving_liquid_symbol_and_preserves_direction(self):
        engine = USEquityHeatEngine("fixture", USHeatConfig(min_heat_score=0))
        for minute in range(6):
            engine.ingest(bar("AAPL", minute, 200 + minute * 1.5, 100_000 * (minute + 1)))
            engine.ingest(bar("SPY", minute, 500 + minute * 0.05, 500_000))
            engine.ingest(bar("NVDA", minute, 180 - minute * 1.0, 200_000 * (minute + 1)))
        report = engine.report()
        by_symbol = {item.symbol: item for item in report.candidates}
        self.assertEqual(report.schema_version, "us-equity-heat/v0.1")
        self.assertEqual(report.tracked_symbols, 3)
        self.assertEqual(report.candidates[0].symbol, "AAPL")
        self.assertEqual(by_symbol["AAPL"].direction, "up")
        self.assertEqual(by_symbol["NVDA"].direction, "down")
        self.assertEqual(by_symbol["AAPL"].option_tradability_status, "not_evaluated")

    def test_updated_bar_replaces_existing_minute(self):
        engine = USEquityHeatEngine("fixture", USHeatConfig(min_heat_score=0))
        for minute in range(3):
            engine.ingest(bar("AAPL", minute, 200 + minute, 100_000))
        updated = bar("AAPL", 2, 210, 900_000)
        report = engine.ingest(updated)
        self.assertEqual(report.candidates[0].bar_count, 3)
        self.assertEqual(report.candidates[0].price, 210)

    def test_extended_hours_bar_is_ignored(self):
        engine = USEquityHeatEngine("fixture", USHeatConfig(min_heat_score=0))
        after_hours = bar(
            "AAPL", 0, 200, 100_000,
            timestamp=datetime(2026, 8, 14, 21, 0, tzinfo=timezone.utc),
        )
        report = engine.ingest(after_hours)
        self.assertEqual(report.input_bar_count, 0)
        self.assertEqual(report.tracked_symbols, 0)

    def test_new_session_clears_previous_day_window(self):
        engine = USEquityHeatEngine("fixture", USHeatConfig(min_heat_score=0))
        for minute in range(3):
            engine.ingest(bar("AAPL", minute, 200 + minute, 100_000))
        next_day = bar(
            "NVDA", 0, 180, 100_000,
            timestamp=datetime(2026, 8, 17, 13, 30, tzinfo=timezone.utc),
        )
        report = engine.ingest(next_day)
        self.assertEqual(report.tracked_symbols, 1)
        self.assertEqual(report.input_bar_count, 1)
        self.assertEqual(report.candidates, ())


class CaptureNotifier:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class FailingNotifier:
    async def send(self, message):
        raise RuntimeError("offline")


class FixtureStream:
    name = "fixture-stream"

    def __init__(self, bars):
        self.bars = bars

    async def stream_bars(self):
        for item in self.bars:
            yield item


class RunnerTests(unittest.TestCase):
    def test_replay_publishes_final_rank_and_persists_report(self):
        bars = [bar("AAPL", minute, 200 + minute * 2, 100_000 * (minute + 1))
                for minute in range(6)]
        notifier = CaptureNotifier()
        with TemporaryDirectory() as directory:
            output = Path(directory, "reports.jsonl")
            runner = USLiveRadarRunner(
                FixtureStream(bars), notifier,
                USHeatConfig(min_heat_score=0),
                push_interval_seconds=10_000,
                report_path=output,
            )
            report = asyncio.run(runner.run())
            self.assertEqual(report.candidates[0].symbol, "AAPL")
            self.assertEqual(len(notifier.messages), 1)
            stored = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(stored["candidates"][0]["symbol"], "AAPL")
            self.assertIn("期权价差", notifier.messages[0])

    def test_jsonl_provider_skips_non_bar_messages(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "bars.jsonl")
            values = [
                {"T": "success", "msg": "connected"},
                {"T": "b", "S": "AAPL", "t": "2026-08-14T13:30:00Z",
                 "o": 200, "h": 201, "l": 199, "c": 200.5,
                 "v": 1000, "vw": 200.2, "n": 10},
            ]
            path.write_text("\n".join(json.dumps(item) for item in values), encoding="utf-8")

            async def collect():
                return [item async for item in JsonLineBarStream(path).stream_bars()]

            bars = asyncio.run(collect())
            self.assertEqual([item.symbol for item in bars], ["AAPL"])

    def test_formatter_labels_option_stage_as_not_evaluated(self):
        engine = USEquityHeatEngine("fixture", USHeatConfig(min_heat_score=0))
        for minute in range(3):
            report = engine.ingest(bar("AAPL", minute, 200 + minute, 500_000))
        message = format_us_heat_report(report)
        self.assertIn("AAPL", message)
        self.assertIn("尚未评估", message)

    def test_composite_notifier_isolates_delivery_failure(self):
        capture = CaptureNotifier()
        with self.assertLogs(level="ERROR"):
            asyncio.run(CompositeNotifier([FailingNotifier(), capture]).send("hello"))
        self.assertEqual(capture.messages, ["hello"])


if __name__ == "__main__":
    unittest.main()
