from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantos_market_data.providers import EastmoneyAShareProvider, load_theme_map


class ProviderTests(unittest.TestCase):
    def test_fetches_all_pages_by_vendor_total_not_valid_row_count(self):
        valid = {
            "f2": 10, "f3": 1, "f5": 100, "f6": 1000, "f7": 2,
            "f8": 1, "f10": 1, "f12": "000001", "f13": 0,
            "f14": "平安银行", "f18": 9.9, "f22": 0,
        }

        class PagedProvider(EastmoneyAShareProvider):
            def __init__(self):
                super().__init__(page_size=2, page_delay=0)
                self.pages = []

            def _fetch_page(self, page):
                self.pages.append(page)
                rows = [valid, {"f12": "bad"}] if page == 1 else [
                    {**valid, "f12": "600000", "f13": 1}
                ]
                return {"data": {"total": 3, "diff": rows}}

        provider = PagedProvider()
        quotes = provider.fetch_quotes()
        self.assertEqual(provider.pages, [1, 2])
        self.assertEqual([item.symbol for item in quotes], ["000001", "600000"])

    def test_normalizes_vendor_fields_and_exchange(self):
        provider = EastmoneyAShareProvider(theme_map={"600000": ("银行",)})
        quote = provider._normalize({
            "f2": 10.5, "f3": 5, "f5": 1000, "f6": 2000,
            "f7": 6, "f8": 3, "f10": 2, "f12": "600000",
            "f13": 1, "f14": "浦发银行", "f18": 10, "f22": 0.5,
        }, datetime(2026, 8, 16, tzinfo=timezone.utc))
        self.assertIsNotNone(quote)
        self.assertEqual(quote.exchange, "XSHG")
        self.assertEqual(quote.themes, ("银行",))

    def test_skips_suspended_or_malformed_quote(self):
        provider = EastmoneyAShareProvider()
        quote = provider._normalize(
            {"f12": "000001", "f2": "-", "f18": 10},
            datetime(2026, 8, 16, tzinfo=timezone.utc),
        )
        self.assertIsNone(quote)

    def test_rejects_page_size_above_vendor_limit(self):
        with self.assertRaisesRegex(ValueError, "limit of 100"):
            EastmoneyAShareProvider(page_size=101)

    def test_loads_both_theme_map_orientations(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "themes.json")
            path.write_text(json.dumps({"算力": ["000001", "600000"]}), encoding="utf-8")
            self.assertEqual(load_theme_map(path)["000001"], ("算力",))
            path.write_text(json.dumps({"000001": ["算力", "AI"]}), encoding="utf-8")
            self.assertEqual(load_theme_map(path)["000001"], ("AI", "算力"))


if __name__ == "__main__":
    unittest.main()
