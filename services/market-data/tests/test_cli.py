from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantos_market_data.cli import main


class CliTests(unittest.TestCase):
    def test_json_replay_emits_report(self):
        with TemporaryDirectory() as directory:
            snapshot = Path(directory, "quotes.json")
            state = Path(directory, "state.json")
            snapshot.write_text(json.dumps([{
                "symbol": "000001", "name": "平安银行", "exchange": "XSHE",
                "timestamp": "2026-08-16T01:00:00+00:00", "price": 10,
                "prev_close": 9, "change_pct": 8, "volume": 100,
                "amount": 200_000_000, "turnover_rate": 9, "volume_ratio": 3,
                "amplitude_pct": 9, "themes": ["银行"],
            }], ensure_ascii=False), encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = main(["--provider", "json", "--input", str(snapshot),
                             "--state", str(state)])
            payload = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(payload["quote_count"], 1)
            self.assertEqual(payload["themes"][0]["theme"], "银行")


if __name__ == "__main__":
    unittest.main()
