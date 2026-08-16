import asyncio
from datetime import date, datetime, timezone
import unittest

from quantos_market_data.options import (
    AlpacaOptionChainProvider,
    OptionTradabilityConfig,
    OptionTradabilityScorer,
    USOptionRadarService,
)
from quantos_market_data.options_models import OptionContractSnapshot
from quantos_market_data.us_models import USHeatCandidate, USMarketHeatReport


NOW = datetime(2026, 8, 14, 13, 35, tzinfo=timezone.utc)


def contract(symbol="AAPL260821C00210000", *, option_type="call", bid=4.9,
             ask=5.1, age=2, volume=2400, interest=5800, delta=0.51,
             feed="opra"):
    return OptionContractSnapshot(
        contract_symbol=symbol,
        underlying_symbol="AAPL",
        expiration_date=date(2026, 8, 21),
        option_type=option_type,
        strike_price=210,
        bid_price=bid,
        ask_price=ask,
        bid_size=20,
        ask_size=20,
        quote_timestamp=datetime.fromtimestamp(NOW.timestamp() - age, timezone.utc),
        daily_volume=volume,
        open_interest=interest,
        implied_volatility=0.5,
        delta=delta,
        feed=feed,
    )


def candidate(direction="up"):
    return USHeatCandidate(
        symbol="AAPL", heat_score=80, underlying_liquidity_score=85,
        direction=direction, price=210, change_1m_pct=1, change_5m_pct=5,
        momentum_acceleration_pct=0.5, volume_ratio_5m=3,
        dollar_volume_5m=500_000_000, range_pct=2,
        vwap_distance_pct=1, bar_count=6,
    )


class TradabilityTests(unittest.TestCase):
    def test_liquid_fresh_contract_is_eligible(self):
        result = OptionTradabilityScorer().score(contract(), NOW)
        self.assertTrue(result.eligible)
        self.assertGreater(result.score, 60)
        self.assertEqual(result.risk_flags, ())

    def test_wide_stale_contract_is_blocked(self):
        result = OptionTradabilityScorer().score(
            contract(bid=1, ask=2, age=60, volume=2, interest=5), NOW
        )
        self.assertFalse(result.eligible)
        self.assertIn("wide_spread", result.risk_flags)
        self.assertIn("stale_quote", result.risk_flags)

    def test_indicative_feed_is_disclosed(self):
        result = OptionTradabilityScorer().score(contract(feed="indicative"), NOW)
        self.assertIn("indicative_feed", result.risk_flags)


class FixtureChain:
    name = "fixture-options"

    def fetch_chain(self, underlying_symbol, underlying_price, as_of):
        return [
            contract(),
            contract("AAPL260821P00210000", option_type="put", delta=-0.49),
        ]


class OptionServiceTests(unittest.TestCase):
    def test_direction_aligns_contract_type(self):
        report = USMarketHeatReport(
            schema_version="us-equity-heat/v0.1", generated_at=NOW,
            source="fixture-equity", input_bar_count=6, tracked_symbols=1,
            candidates=(candidate("up"),),
        )
        output = asyncio.run(USOptionRadarService(FixtureChain()).enrich(report))
        self.assertEqual(output.schema_version, "us-options-radar/v0.1")
        self.assertEqual(output.underlyings[0].status, "ready")
        self.assertTrue(all(item.option_type == "call"
                            for item in output.underlyings[0].contracts))
        serialized = output.to_dict()
        self.assertEqual(serialized["underlyings"][0]["contracts"][0]["expiration_date"],
                         "2026-08-21")

    def test_provider_failure_is_visible(self):
        class Broken:
            name = "broken"

            def fetch_chain(self, *args):
                raise RuntimeError("entitlement denied")

        report = USMarketHeatReport(
            schema_version="us-equity-heat/v0.1", generated_at=NOW,
            source="fixture", input_bar_count=6, tracked_symbols=1,
            candidates=(candidate(),),
        )
        output = asyncio.run(USOptionRadarService(Broken()).enrich(report))
        self.assertEqual(output.underlyings[0].status, "unavailable")
        self.assertIn("entitlement", output.underlyings[0].error)


class AlpacaOptionProviderTests(unittest.TestCase):
    def test_occ_symbol_terms_and_vendor_normalization(self):
        provider = AlpacaOptionChainProvider("key", "secret")
        terms = provider._contract_terms("AAPL260821C00210000")
        self.assertEqual(terms, (date(2026, 8, 21), "call", 210.0))
        value = provider._normalize(
            "AAPL260821C00210000",
            {
                "latestQuote": {"bp": 4.9, "ap": 5.1, "bs": 20, "as": 21,
                                "t": "2026-08-14T13:34:58Z"},
                "latestTrade": {"p": 5.0},
                "dailyBar": {"v": 2000},
                "impliedVolatility": 0.5,
                "greeks": {"delta": 0.51, "gamma": 0.04, "theta": -0.2, "vega": 0.1},
            },
            {"open_interest": "5800"},
            "AAPL",
        )
        self.assertEqual(value.open_interest, 5800)
        self.assertEqual(value.delta, 0.51)


if __name__ == "__main__":
    unittest.main()
