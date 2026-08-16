"""Rolling heat calculations and live runner for US equity candidates."""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, replace
from datetime import datetime, time as wall_time, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .alpaca import USBarStreamProvider
from .notifiers import Notifier, format_us_heat_report
from .us_models import USEquityBar, USHeatCandidate, USMarketHeatReport


NEW_YORK = ZoneInfo("America/New_York")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


def is_regular_session(timestamp: datetime) -> bool:
    local = timestamp.astimezone(NEW_YORK)
    return (
        local.weekday() < 5
        and wall_time(9, 30) <= local.time().replace(tzinfo=None) < wall_time(16, 0)
    )


@dataclass(frozen=True)
class USHeatConfig:
    window_bars: int = 30
    min_bars: int = 3
    top_n: int = 20
    min_heat_score: float = 35.0
    min_price: float = 2.0
    min_dollar_volume_5m: float = 1_000_000.0

    def __post_init__(self) -> None:
        if self.window_bars < 6 or self.min_bars < 3:
            raise ValueError("window_bars must be at least 6 and min_bars at least 3")
        if self.min_bars > self.window_bars:
            raise ValueError("min_bars cannot exceed window_bars")
        if self.top_n < 1 or min(self.min_heat_score, self.min_price,
                                 self.min_dollar_volume_5m) < 0:
            raise ValueError("ranking configuration must be non-negative")


class USEquityHeatEngine:
    def __init__(self, source: str, config: USHeatConfig | None = None) -> None:
        self.source = source
        self.config = config or USHeatConfig()
        self._bars: dict[str, dict[datetime, USEquityBar]] = {}
        self.input_bar_count = 0
        self._session_date = None

    def ingest(self, bar: USEquityBar) -> USMarketHeatReport:
        if is_regular_session(bar.timestamp):
            session_date = bar.timestamp.astimezone(NEW_YORK).date()
            if self._session_date is not None and session_date != self._session_date:
                self._bars.clear()
                self.input_bar_count = 0
            self._session_date = session_date
            window = self._bars.setdefault(bar.symbol, {})
            window[bar.timestamp] = bar
            if len(window) > self.config.window_bars:
                for timestamp in sorted(window)[:-self.config.window_bars]:
                    del window[timestamp]
            self.input_bar_count += 1
        return self.report(bar.timestamp)

    def report(self, generated_at: datetime | None = None) -> USMarketHeatReport:
        generated_at = generated_at or datetime.now(timezone.utc)
        candidates: list[USHeatCandidate] = []
        for symbol, values in self._bars.items():
            bars = [values[key] for key in sorted(values)]
            candidate = self._score(symbol, bars)
            if candidate is not None:
                candidates.append(candidate)
        candidates.sort(
            key=lambda item: (-item.heat_score, -item.underlying_liquidity_score,
                              item.symbol)
        )
        candidates = [
            item for item in candidates
            if item.heat_score >= self.config.min_heat_score
        ][:self.config.top_n]
        return USMarketHeatReport(
            schema_version="us-equity-heat/v0.1",
            generated_at=generated_at,
            source=self.source,
            input_bar_count=self.input_bar_count,
            tracked_symbols=len(self._bars),
            candidates=tuple(candidates),
        )

    def _score(self, symbol: str, bars: list[USEquityBar]) -> USHeatCandidate | None:
        cfg = self.config
        if len(bars) < cfg.min_bars:
            return None
        current = bars[-1]
        recent = bars[-5:]
        dollar_volume = sum(item.close * item.volume for item in recent)
        if current.close < cfg.min_price or dollar_volume < cfg.min_dollar_volume_5m:
            return None
        change_1m = (current.close / bars[-2].close - 1.0) * 100.0
        anchor = bars[max(0, len(bars) - 6)]
        change_5m = (current.close / anchor.close - 1.0) * 100.0
        previous_change = (bars[-2].close / bars[-3].close - 1.0) * 100.0
        acceleration = change_1m - previous_change
        prior_volumes = [item.volume for item in bars[-6:-1]]
        mean_prior_volume = sum(prior_volumes) / len(prior_volumes)
        volume_ratio = current.volume / mean_prior_volume if mean_prior_volume else 0.0
        range_pct = (current.high - current.low) / current.open * 100.0
        vwap_distance = (current.close / current.vwap - 1.0) * 100.0
        momentum_component = _clamp(abs(change_5m) / 4.0)
        volume_component = _clamp(math.log1p(volume_ratio) / math.log(6.0))
        dollar_component = _clamp(math.log10(max(dollar_volume, 1.0)) / 9.0)
        heat_score = 100.0 * (
            0.30 * momentum_component
            + 0.25 * volume_component
            + 0.20 * dollar_component
            + 0.10 * _clamp(range_pct / 2.0)
            + 0.10 * _clamp(abs(vwap_distance) / 2.0)
            + 0.05 * _clamp(abs(acceleration) / 1.0)
        )
        price_fit = 1.0 if 5.0 <= current.close <= 1_000.0 else 0.4
        liquidity_score = 100.0 * (
            0.70 * dollar_component + 0.30 * price_fit
        )
        direction = "up" if change_5m >= 0.15 else "down" if change_5m <= -0.15 else "flat"
        return USHeatCandidate(
            symbol=symbol,
            heat_score=round(heat_score, 4),
            underlying_liquidity_score=round(liquidity_score, 4),
            direction=direction,
            price=round(current.close, 4),
            change_1m_pct=round(change_1m, 4),
            change_5m_pct=round(change_5m, 4),
            momentum_acceleration_pct=round(acceleration, 4),
            volume_ratio_5m=round(volume_ratio, 4),
            dollar_volume_5m=round(dollar_volume, 2),
            range_pct=round(range_pct, 4),
            vwap_distance_pct=round(vwap_distance, 4),
            bar_count=len(bars),
        )


class JsonLineReportStore:
    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path) if path else None

    def append(self, report) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")


class USLiveRadarRunner:
    def __init__(
        self,
        provider: USBarStreamProvider,
        notifier: Notifier,
        config: USHeatConfig | None = None,
        push_interval_seconds: float = 300.0,
        report_path: str | Path | None = None,
        option_service=None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if push_interval_seconds < 0:
            raise ValueError("push_interval_seconds must be non-negative")
        self.provider = provider
        self.notifier = notifier
        self.engine = USEquityHeatEngine(provider.name, config)
        self.push_interval_seconds = push_interval_seconds
        self.store = JsonLineReportStore(report_path)
        self.monotonic = monotonic
        self.option_service = option_service

    async def run(self) -> USMarketHeatReport:
        last_push = self.monotonic()
        latest = self.engine.report()
        last_pushed_bar_count = -1
        async for bar in self.provider.stream_bars():
            latest = self.engine.ingest(bar)
            now = self.monotonic()
            if latest.candidates and now - last_push >= self.push_interval_seconds:
                await self._publish(latest)
                last_push = now
                last_pushed_bar_count = latest.input_bar_count
        if latest.candidates and latest.input_bar_count != last_pushed_bar_count:
            await self._publish(latest)
        return latest

    async def _publish(self, report: USMarketHeatReport) -> None:
        if self.option_service is None:
            output = report
            message = format_us_heat_report(report)
        else:
            from .notifiers import format_us_options_report

            output = await self.option_service.enrich(report)
            message = format_us_options_report(output)
        self.store.append(output)
        await self.notifier.send(message)
