from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantos_market_data.models import StockQuote
from quantos_market_data.radar import AnomalyDetector, MarketRadarService, RadarConfig


NOW = datetime(2026, 8, 16, 2, tzinfo=timezone.utc)


def quote(symbol, change, *, turnover=2, ratio=1, amplitude=3, speed=0,
          amount=20_000_000, themes=("算力",)):
    return StockQuote(
        symbol=symbol, name=f"股票{symbol}", exchange="XSHG" if symbol.startswith("6") else "XSHE",
        timestamp=NOW, price=10, prev_close=10, change_pct=change,
        volume=1_000_000, amount=amount, turnover_rate=turnover,
        volume_ratio=ratio, amplitude_pct=amplitude, change_5m_pct=speed,
        themes=themes,
    )


class FixtureProvider:
    name = "fixture"

    def __init__(self, quotes):
        self.quotes = quotes

    def fetch_quotes(self):
        return self.quotes


class AnomalyTests(unittest.TestCase):
    def test_rejects_inconsistent_thresholds(self):
        with self.assertRaisesRegex(ValueError, "extreme price"):
            RadarConfig(price_change_pct=8, extreme_price_change_pct=7)

    def test_requires_two_triggers_for_non_extreme_move(self):
        detector = AnomalyDetector(RadarConfig())
        self.assertEqual(detector.detect([quote("000001", 5.5)]), [])
        found = detector.detect([quote("000001", 5.5, ratio=3)])
        self.assertEqual(found[0].reasons, ("price_surge", "high_volume_ratio"))

    def test_extreme_price_move_is_sufficient(self):
        found = AnomalyDetector(RadarConfig()).detect([quote("000001", -7.2)])
        self.assertEqual(found[0].direction, "down")
        self.assertIn("price_plunge", found[0].reasons)

    def test_results_are_score_sorted(self):
        found = AnomalyDetector(RadarConfig()).detect([
            quote("000001", 5.5, ratio=3),
            quote("000002", 9.5, turnover=18, ratio=4, amount=500_000_000),
        ])
        self.assertEqual(found[0].symbol, "000002")


class ServiceTests(unittest.TestCase):
    def test_report_aggregates_theme_and_anomalies(self):
        service = MarketRadarService(FixtureProvider([
            quote("000001", 8, ratio=3),
            quote("000002", 2),
            quote("600000", -1, themes=("银行",)),
        ]))
        report = service.run(NOW)
        self.assertEqual(report.schema_version, "market-radar/v0.1")
        self.assertEqual(report.quote_count, 3)
        self.assertEqual(report.anomalies[0].symbol, "000001")
        themes = {item.theme: item for item in report.themes}
        self.assertEqual(themes["算力"].stock_count, 2)
        self.assertEqual(themes["算力"].anomaly_count, 1)

    def test_three_snapshots_produce_acceleration(self):
        with TemporaryDirectory() as directory:
            state = Path(directory, "state.json")
            first = MarketRadarService(FixtureProvider([quote("000001", -2)]), state_path=state)
            first.run(NOW - timedelta(hours=2))
            second = MarketRadarService(FixtureProvider([quote("000001", 1)]), state_path=state)
            second.run(NOW - timedelta(hours=1))
            third = MarketRadarService(
                FixtureProvider([quote("000001", 8, ratio=3)]), state_path=state
            )
            result = third.run(NOW).themes[0]
            self.assertGreater(result.velocity_per_hour, 0)
            self.assertGreater(result.acceleration_per_hour2, 0)
            history = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(len(history), 3)


if __name__ == "__main__":
    unittest.main()
