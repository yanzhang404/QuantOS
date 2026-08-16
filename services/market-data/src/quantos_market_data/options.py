"""Option-chain acquisition and contract tradability scoring."""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .options_models import (
    OptionContractSnapshot,
    OptionTradability,
    UnderlyingOptionSelection,
    USOptionsRadarReport,
)
from .us_models import USHeatCandidate, USMarketHeatReport


OCC_PATTERN = re.compile(r"^([A-Z0-9.]+)(\d{6})([CP])(\d{8})$")


class OptionChainProvider(Protocol):
    name: str

    def fetch_chain(
        self, underlying_symbol: str, underlying_price: float, as_of: datetime
    ) -> Sequence[OptionContractSnapshot]: ...


class JsonOptionChainProvider:
    name = "json-option-chain"

    def __init__(self, path: str | Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = payload["contracts"] if isinstance(payload, dict) else payload
        self.contracts = [OptionContractSnapshot.from_dict(item) for item in rows]

    def fetch_chain(
        self, underlying_symbol: str, underlying_price: float, as_of: datetime
    ) -> list[OptionContractSnapshot]:
        return [item for item in self.contracts if item.underlying_symbol == underlying_symbol]


class AlpacaOptionChainProvider:
    """Read option snapshots and metadata; never accesses accounts or orders."""

    snapshots_endpoint = "https://data.alpaca.markets/v1beta1/options/snapshots"
    contracts_endpoint = "https://paper-api.alpaca.markets/v2/options/contracts"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        feed: str = "opra",
        max_dte: int = 7,
        strike_band: float = 0.20,
        timeout: float = 15.0,
        retries: int = 2,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("Alpaca API key and secret are required")
        if feed not in {"opra", "indicative"}:
            raise ValueError("option feed must be opra or indicative")
        if max_dte < 0 or not 0 < strike_band < 1 or timeout <= 0 or retries < 0:
            raise ValueError("invalid option-chain request limits")
        self.api_key = api_key
        self.api_secret = api_secret
        self.feed = feed
        self.max_dte = max_dte
        self.strike_band = strike_band
        self.timeout = timeout
        self.retries = retries
        self.name = f"alpaca-options-{feed}"

    def fetch_chain(
        self, underlying_symbol: str, underlying_price: float, as_of: datetime
    ) -> list[OptionContractSnapshot]:
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        session_date = as_of.date()
        expiration_end = session_date + timedelta(days=self.max_dte)
        common = {
            "expiration_date_gte": session_date.isoformat(),
            "expiration_date_lte": expiration_end.isoformat(),
            "strike_price_gte": round(underlying_price * (1.0 - self.strike_band), 4),
            "strike_price_lte": round(underlying_price * (1.0 + self.strike_band), 4),
            "limit": 1000,
        }
        snapshots = self._fetch_pages(
            f"{self.snapshots_endpoint}/{underlying_symbol}",
            {**common, "feed": self.feed},
            "snapshots",
        )
        metadata_rows = self._fetch_pages(
            self.contracts_endpoint,
            {**common, "underlying_symbols": underlying_symbol, "status": "active"},
            "option_contracts",
        )
        metadata = {str(item.get("symbol")): item for item in metadata_rows}
        result: list[OptionContractSnapshot] = []
        invalid_rows = 0
        for symbol, snapshot in snapshots.items():
            try:
                normalized = self._normalize(
                    symbol, snapshot, metadata.get(symbol, {}), underlying_symbol
                )
            except (KeyError, TypeError, ValueError):
                invalid_rows += 1
                continue
            if normalized is not None:
                result.append(normalized)
        if snapshots and not result and invalid_rows:
            raise RuntimeError("Alpaca option chain contained no valid contract snapshots")
        return result

    def _fetch_pages(self, url: str, params: dict[str, Any], result_key: str):
        combined: dict | list = {} if result_key == "snapshots" else []
        page_token = None
        while True:
            query = dict(params)
            if page_token:
                query["page_token"] = page_token
            payload = self._get_json(f"{url}?{urlencode(query)}")
            rows = payload.get(result_key, {} if result_key == "snapshots" else [])
            if isinstance(combined, dict):
                if not isinstance(rows, dict):
                    raise RuntimeError(f"Alpaca {result_key} response must be an object")
                combined.update(rows)
            else:
                if not isinstance(rows, list):
                    raise RuntimeError(f"Alpaca {result_key} response must be a list")
                combined.extend(rows)
            page_token = payload.get("next_page_token")
            if not page_token:
                return combined

    def _get_json(self, url: str) -> dict[str, Any]:
        request = Request(url, headers={
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Accept": "application/json",
            "User-Agent": "QuantOS-USOptionsRadar/0.1",
        })
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code in {401, 403}:
                    raise RuntimeError(f"Alpaca option data rejected with HTTP {exc.code}") from exc
                last_error = exc
            except Exception as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError(f"failed to fetch Alpaca option data: {last_error}")

    def _normalize(
        self, symbol: str, snapshot: dict, metadata: dict, underlying: str
    ) -> OptionContractSnapshot | None:
        quote = snapshot.get("latestQuote") or snapshot.get("latest_quote") or {}
        timestamp = quote.get("t") or quote.get("timestamp")
        if not timestamp:
            return None
        parsed = self._contract_terms(symbol)
        if parsed is None and not metadata:
            return None
        expiration, option_type, strike = parsed or (
            date.fromisoformat(metadata["expiration_date"]),
            str(metadata["type"]),
            float(metadata["strike_price"]),
        )
        greeks = snapshot.get("greeks") or {}
        daily = snapshot.get("dailyBar") or snapshot.get("daily_bar") or {}
        trade = snapshot.get("latestTrade") or snapshot.get("latest_trade") or {}
        return OptionContractSnapshot(
            contract_symbol=symbol,
            underlying_symbol=underlying,
            expiration_date=expiration,
            option_type=option_type,
            strike_price=strike,
            bid_price=float(quote.get("bp") or quote.get("bid_price") or 0),
            ask_price=float(quote.get("ap") or quote.get("ask_price") or 0),
            bid_size=int(quote.get("bs") or quote.get("bid_size") or 0),
            ask_size=int(quote.get("as") or quote.get("ask_size") or 0),
            quote_timestamp=datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")),
            latest_trade_price=self._optional_float(trade.get("p") or trade.get("price")),
            daily_volume=self._optional_int(daily.get("v") or daily.get("volume")),
            open_interest=self._optional_int(metadata.get("open_interest")),
            implied_volatility=self._optional_float(
                snapshot.get("impliedVolatility", snapshot.get("implied_volatility"))
            ),
            delta=self._optional_float(greeks.get("delta")),
            gamma=self._optional_float(greeks.get("gamma")),
            theta=self._optional_float(greeks.get("theta")),
            vega=self._optional_float(greeks.get("vega")),
            feed=self.feed,
        )

    @staticmethod
    def _contract_terms(symbol: str):
        match = OCC_PATTERN.match(symbol)
        if not match:
            return None
        expiration = datetime.strptime(match.group(2), "%y%m%d").date()
        option_type = "call" if match.group(3) == "C" else "put"
        strike = int(match.group(4)) / 1000.0
        return expiration, option_type, strike

    @staticmethod
    def _optional_float(value):
        return None if value in (None, "") else float(value)

    @staticmethod
    def _optional_int(value):
        return None if value in (None, "") else int(value)


@dataclass(frozen=True)
class OptionTradabilityConfig:
    max_dte: int = 7
    max_spread_pct: float = 15.0
    max_quote_age_seconds: float = 30.0
    min_daily_volume: int = 20
    min_open_interest: int = 100
    min_score: float = 60.0
    contracts_per_underlying: int = 3

    def __post_init__(self) -> None:
        if self.max_dte < 0 or self.min_daily_volume < 0 or self.min_open_interest < 0:
            raise ValueError("option limits must be non-negative")
        if min(self.max_spread_pct, self.max_quote_age_seconds) <= 0:
            raise ValueError("spread and quote-age limits must be positive")
        if not 0 <= self.min_score <= 100 or self.contracts_per_underlying < 1:
            raise ValueError("option score must be 0-100 and contract count positive")


class OptionTradabilityScorer:
    def __init__(self, config: OptionTradabilityConfig | None = None) -> None:
        self.config = config or OptionTradabilityConfig()

    def score(
        self, snapshot: OptionContractSnapshot, as_of: datetime
    ) -> OptionTradability | None:
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        dte = (snapshot.expiration_date - as_of.date()).days
        if dte < 0 or dte > self.config.max_dte:
            return None
        mid = (snapshot.bid_price + snapshot.ask_price) / 2.0
        spread_pct = (
            (snapshot.ask_price - snapshot.bid_price) / mid * 100.0 if mid > 0 else 100.0
        )
        age = max(0.0, (as_of - snapshot.quote_timestamp).total_seconds())
        volume = snapshot.daily_volume
        interest = snapshot.open_interest
        flags: list[str] = []
        if snapshot.bid_price <= 0 or snapshot.ask_price <= 0:
            flags.append("no_two_sided_market")
        if spread_pct > self.config.max_spread_pct:
            flags.append("wide_spread")
        if age > self.config.max_quote_age_seconds:
            flags.append("stale_quote")
        if volume is None:
            flags.append("missing_volume")
        elif volume < self.config.min_daily_volume:
            flags.append("low_volume")
        if interest is None:
            flags.append("missing_open_interest")
        elif interest < self.config.min_open_interest:
            flags.append("low_open_interest")
        if dte == 0:
            flags.append("zero_dte")
        if snapshot.feed == "indicative":
            flags.append("indicative_feed")
        if snapshot.implied_volatility is not None and snapshot.implied_volatility > 1.5:
            flags.append("extreme_iv")
        spread_component = _clamp(1.0 - spread_pct / self.config.max_spread_pct)
        freshness_component = _clamp(1.0 - age / self.config.max_quote_age_seconds)
        volume_component = _clamp(math.log10((volume or 0) + 1) / 4.0)
        interest_component = _clamp(math.log10((interest or 0) + 1) / 4.0)
        delta_component = 0.0
        if snapshot.delta is not None:
            absolute_delta = abs(snapshot.delta)
            delta_component = 1.0 if 0.25 <= absolute_delta <= 0.70 else 0.35
        price_component = 1.0 if 0.25 <= mid <= 20.0 else 0.3
        score = 100.0 * (
            0.35 * spread_component
            + 0.15 * freshness_component
            + 0.15 * volume_component
            + 0.15 * interest_component
            + 0.10 * delta_component
            + 0.10 * price_component
        )
        blocking = {
            "no_two_sided_market", "wide_spread", "stale_quote",
            "missing_volume", "low_volume", "missing_open_interest", "low_open_interest",
        }
        eligible = score >= self.config.min_score and not blocking.intersection(flags)
        return OptionTradability(
            contract_symbol=snapshot.contract_symbol,
            option_type=snapshot.option_type,
            expiration_date=snapshot.expiration_date,
            strike_price=snapshot.strike_price,
            score=round(score, 4),
            eligible=eligible,
            mid_price=round(mid, 4),
            spread_pct=round(spread_pct, 4),
            quote_age_seconds=round(age, 3),
            daily_volume=volume,
            open_interest=interest,
            implied_volatility=snapshot.implied_volatility,
            delta=snapshot.delta,
            risk_flags=tuple(flags),
        )


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


class USOptionRadarService:
    def __init__(
        self,
        provider: OptionChainProvider,
        scorer: OptionTradabilityScorer | None = None,
        top_underlyings: int = 10,
    ) -> None:
        self.provider = provider
        self.scorer = scorer or OptionTradabilityScorer()
        self.top_underlyings = top_underlyings

    async def enrich(self, equity_report: USMarketHeatReport) -> USOptionsRadarReport:
        selections = await asyncio.gather(*(
            self._select(candidate, equity_report.generated_at)
            for candidate in equity_report.candidates[:self.top_underlyings]
        ))
        return USOptionsRadarReport(
            schema_version="us-options-radar/v0.1",
            generated_at=equity_report.generated_at,
            equity_source=equity_report.source,
            options_source=self.provider.name,
            underlyings=tuple(selections),
        )

    async def _select(
        self, candidate: USHeatCandidate, as_of: datetime
    ) -> UnderlyingOptionSelection:
        try:
            chain = await asyncio.to_thread(
                self.provider.fetch_chain, candidate.symbol, candidate.price, as_of
            )
        except Exception as exc:
            return UnderlyingOptionSelection(
                symbol=candidate.symbol,
                heat_score=candidate.heat_score,
                direction=candidate.direction,
                underlying_price=candidate.price,
                status="unavailable",
                contracts_considered=0,
                contracts=(),
                error=str(exc)[:200],
            )
        aligned_type = "call" if candidate.direction == "up" else "put" if candidate.direction == "down" else None
        scored = [
            result for item in chain
            if aligned_type is None or item.option_type == aligned_type
            if (result := self.scorer.score(item, as_of)) is not None
        ]
        scored.sort(key=lambda item: (-item.eligible, -item.score, item.spread_pct,
                                      item.contract_symbol))
        selected = scored[:self.scorer.config.contracts_per_underlying]
        status = "ready" if any(item.eligible for item in selected) else "no_eligible_contract"
        return UnderlyingOptionSelection(
            symbol=candidate.symbol,
            heat_score=candidate.heat_score,
            direction=candidate.direction,
            underlying_price=candidate.price,
            status=status,
            contracts_considered=len(scored),
            contracts=tuple(selected),
        )
