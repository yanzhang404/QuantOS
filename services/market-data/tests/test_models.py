from datetime import datetime, timezone
import unittest

from quantos_market_data.models import StockQuote


class StockQuoteTests(unittest.TestCase):
    def test_rejects_naive_timestamp(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            StockQuote(
                symbol="600000", name="浦发银行", exchange="XSHG",
                timestamp=datetime(2026, 8, 16), price=10, prev_close=10,
                change_pct=0, volume=1, amount=1, turnover_rate=0,
                volume_ratio=0, amplitude_pct=0,
            )

    def test_from_dict_deduplicates_themes(self):
        quote = StockQuote.from_dict({
            "symbol": "000001", "name": "平安银行", "exchange": "XSHE",
            "timestamp": "2026-08-16T01:00:00Z", "price": 10,
            "prev_close": 9.8, "change_pct": 2, "volume": 10,
            "amount": 100, "turnover_rate": 1, "volume_ratio": 1,
            "amplitude_pct": 2, "themes": ["银行", "银行", "金融"],
        })
        self.assertEqual(quote.timestamp.tzinfo, timezone.utc)
        self.assertEqual(quote.themes, ("金融", "银行"))


if __name__ == "__main__":
    unittest.main()
