from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantos_market_data.evaluation import RadarOutcomeEvaluator, _Alert
from quantos_market_data.us_models import USEquityBar


NOW = datetime(2026, 8, 14, 13, 35, tzinfo=timezone.utc)


def bar(symbol, minute, close, high, low):
    return USEquityBar(
        symbol=symbol, timestamp=NOW + timedelta(minutes=minute),
        open=100, high=high, low=low, close=close,
        volume=100_000, vwap=close, trade_count=100,
    )


class EvaluationTests(unittest.TestCase):
    def test_directional_outcomes_and_excursions(self):
        alerts = [
            _Alert("AAPL", NOW, "up", 100),
            _Alert("NVDA", NOW, "down", 100),
        ]
        bars = [
            bar("AAPL", 5, 105, 106, 99),
            bar("NVDA", 5, 95, 101, 94),
        ]
        report = RadarOutcomeEvaluator((5, 15)).evaluate(alerts, bars)
        complete = [item for item in report.outcomes if item.complete]
        self.assertEqual([item.directional_return_pct for item in complete], [5.0, 5.0])
        self.assertEqual([item.max_favorable_excursion_pct for item in complete], [6.0, 6.0])
        self.assertEqual([item.max_adverse_excursion_pct for item in complete], [-1.0, -1.0])
        self.assertEqual(report.summaries[0].hit_rate, 1.0)
        self.assertEqual(report.summaries[1].complete_count, 0)

    def test_loads_options_report_price_and_deduplicates_alert(self):
        with TemporaryDirectory() as directory:
            reports = Path(directory, "reports.jsonl")
            bars = Path(directory, "bars.jsonl")
            payload = {
                "schema_version": "us-options-radar/v0.1",
                "generated_at": NOW.isoformat(),
                "underlyings": [{
                    "symbol": "AAPL", "direction": "up", "underlying_price": 100,
                }],
            }
            reports.write_text(
                json.dumps(payload) + "\n" + json.dumps(payload) + "\n", encoding="utf-8"
            )
            future = {
                "T": "b", "S": "AAPL", "t": (NOW + timedelta(minutes=5)).isoformat(),
                "o": 100, "h": 106, "l": 99, "c": 105,
                "v": 1000, "vw": 103, "n": 10,
            }
            bars.write_text(json.dumps(future), encoding="utf-8")
            result = RadarOutcomeEvaluator((5,)).evaluate_files(reports, bars)
            self.assertEqual(result.alert_count, 1)
            self.assertEqual(result.outcomes[0].raw_return_pct, 5.0)


if __name__ == "__main__":
    unittest.main()
