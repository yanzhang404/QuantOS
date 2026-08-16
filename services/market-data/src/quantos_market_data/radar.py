"""A-share anomaly, theme heat, and heat-acceleration calculations."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .models import MarketRadarReport, StockAnomaly, StockQuote, ThemeHeat
from .providers import MarketSnapshotProvider


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


@dataclass(frozen=True)
class RadarConfig:
    price_change_pct: float = 5.0
    extreme_price_change_pct: float = 7.0
    turnover_rate: float = 8.0
    volume_ratio: float = 2.0
    amplitude_pct: float = 8.0
    change_5m_pct: float = 1.0
    amount: float = 100_000_000.0
    min_triggers: int = 2
    history_limit: int = 24

    def __post_init__(self) -> None:
        if self.min_triggers < 1 or self.history_limit < 3:
            raise ValueError("min_triggers must be positive and history_limit at least 3")
        thresholds = (
            self.price_change_pct,
            self.extreme_price_change_pct,
            self.turnover_rate,
            self.volume_ratio,
            self.amplitude_pct,
            self.change_5m_pct,
            self.amount,
        )
        if any(value < 0 for value in thresholds):
            raise ValueError("radar thresholds must be non-negative")
        if self.extreme_price_change_pct < self.price_change_pct:
            raise ValueError("extreme price threshold cannot be lower than price threshold")


class AnomalyDetector:
    def __init__(self, config: RadarConfig) -> None:
        self.config = config

    def detect(self, quotes: Iterable[StockQuote]) -> list[StockAnomaly]:
        found: list[StockAnomaly] = []
        for quote in quotes:
            anomaly = self._detect_one(quote)
            if anomaly is not None:
                found.append(anomaly)
        return sorted(found, key=lambda item: (-item.score, item.symbol))

    def _detect_one(self, quote: StockQuote) -> StockAnomaly | None:
        cfg = self.config
        reasons: list[str] = []
        if quote.change_pct >= cfg.price_change_pct:
            reasons.append("price_surge")
        elif quote.change_pct <= -cfg.price_change_pct:
            reasons.append("price_plunge")
        if quote.turnover_rate >= cfg.turnover_rate:
            reasons.append("high_turnover")
        if quote.volume_ratio >= cfg.volume_ratio:
            reasons.append("high_volume_ratio")
        if quote.amplitude_pct >= cfg.amplitude_pct:
            reasons.append("wide_amplitude")
        if abs(quote.change_5m_pct) >= cfg.change_5m_pct:
            reasons.append("fast_move")
        if quote.amount >= cfg.amount:
            reasons.append("high_amount")
        extreme = abs(quote.change_pct) >= cfg.extreme_price_change_pct
        if len(reasons) < cfg.min_triggers and not extreme:
            return None
        score = 100.0 * (
            0.35 * _clamp(abs(quote.change_pct) / 10.0)
            + 0.15 * _clamp(quote.turnover_rate / 20.0)
            + 0.15 * _clamp(quote.volume_ratio / 5.0)
            + 0.10 * _clamp(quote.amplitude_pct / 15.0)
            + 0.10 * _clamp(abs(quote.change_5m_pct) / 3.0)
            + 0.15 * _clamp(math.log10(max(quote.amount, 1.0)) / 10.0)
        )
        direction = "up" if quote.change_pct > 0 else "down" if quote.change_pct < 0 else "flat"
        return StockAnomaly(
            symbol=quote.symbol,
            name=quote.name,
            score=round(score, 4),
            direction=direction,
            reasons=tuple(reasons),
            change_pct=quote.change_pct,
            amount=quote.amount,
        )


class RadarStateStore:
    """Small JSON history used only for cross-snapshot derivatives."""

    def __init__(self, path: str | Path | None, history_limit: int) -> None:
        self.path = Path(path) if path else None
        self.history_limit = history_limit

    def load(self) -> list[dict]:
        if self.path is None or not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("radar state must be a JSON list")
        return payload[-self.history_limit :]

    def save(self, history: list[dict]) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(history[-self.history_limit :], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


class ThemeHeatCalculator:
    def calculate(
        self,
        quotes: Sequence[StockQuote],
        anomalies: Sequence[StockAnomaly],
        generated_at: datetime,
        history: Sequence[dict],
    ) -> list[ThemeHeat]:
        groups: dict[str, list[StockQuote]] = {}
        for quote in quotes:
            for theme in quote.themes:
                if theme.strip():
                    groups.setdefault(theme.strip(), []).append(quote)
        anomaly_symbols = {item.symbol for item in anomalies}
        current_scores = {
            theme: self._score(items, anomaly_symbols) for theme, items in groups.items()
        }
        result: list[ThemeHeat] = []
        for theme, items in groups.items():
            score = current_scores[theme]
            velocity, acceleration = self._derivatives(
                theme, score, generated_at, history
            )
            advancing = sum(item.change_pct > 0 for item in items)
            anomaly_count = sum(item.symbol in anomaly_symbols for item in items)
            result.append(
                ThemeHeat(
                    theme=theme,
                    score=round(score, 4),
                    velocity_per_hour=round(velocity, 4),
                    acceleration_per_hour2=round(acceleration, 4),
                    stock_count=len(items),
                    advancing_ratio=round(advancing / len(items), 4),
                    anomaly_count=anomaly_count,
                    mean_change_pct=round(
                        sum(item.change_pct for item in items) / len(items), 4
                    ),
                    total_amount=round(sum(item.amount for item in items), 2),
                )
            )
        return sorted(
            result,
            key=lambda item: (-item.score, -item.acceleration_per_hour2, item.theme),
        )

    @staticmethod
    def _score(items: Sequence[StockQuote], anomaly_symbols: set[str]) -> float:
        count = len(items)
        mean_change = sum(item.change_pct for item in items) / count
        breadth = sum(item.change_pct > 0 for item in items) / count
        anomaly_ratio = sum(item.symbol in anomaly_symbols for item in items) / count
        mean_turnover = sum(item.turnover_rate for item in items) / count
        return 100.0 * (
            0.30 * _clamp((mean_change + 3.0) / 8.0)
            + 0.25 * breadth
            + 0.30 * anomaly_ratio
            + 0.15 * _clamp(mean_turnover / 10.0)
        )

    @staticmethod
    def _derivatives(
        theme: str, score: float, generated_at: datetime, history: Sequence[dict]
    ) -> tuple[float, float]:
        points: list[tuple[datetime, float]] = []
        for snapshot in history[-2:]:
            theme_score = snapshot.get("scores", {}).get(theme)
            if theme_score is not None:
                points.append(
                    (datetime.fromisoformat(snapshot["timestamp"]), float(theme_score))
                )
        points.append((generated_at, score))
        if len(points) < 2:
            return 0.0, 0.0
        dt_hours = (points[-1][0] - points[-2][0]).total_seconds() / 3600.0
        if dt_hours <= 0:
            return 0.0, 0.0
        velocity = (points[-1][1] - points[-2][1]) / dt_hours
        if len(points) < 3:
            return velocity, 0.0
        previous_hours = (points[-2][0] - points[-3][0]).total_seconds() / 3600.0
        if previous_hours <= 0:
            return velocity, 0.0
        previous_velocity = (points[-2][1] - points[-3][1]) / previous_hours
        acceleration = (velocity - previous_velocity) / ((dt_hours + previous_hours) / 2.0)
        return velocity, acceleration


class MarketRadarService:
    def __init__(
        self,
        provider: MarketSnapshotProvider,
        config: RadarConfig | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        self.provider = provider
        self.config = config or RadarConfig()
        self.detector = AnomalyDetector(self.config)
        self.heat = ThemeHeatCalculator()
        self.state = RadarStateStore(state_path, self.config.history_limit)

    def run(self, generated_at: datetime | None = None) -> MarketRadarReport:
        generated_at = generated_at or datetime.now(timezone.utc)
        if generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        quotes = list(self.provider.fetch_quotes())
        anomalies = self.detector.detect(quotes)
        history = self.state.load()
        themes = self.heat.calculate(quotes, anomalies, generated_at, history)
        history.append(
            {
                "timestamp": generated_at.isoformat(),
                "scores": {item.theme: item.score for item in themes},
            }
        )
        self.state.save(history)
        return MarketRadarReport(
            schema_version="market-radar/v0.1",
            generated_at=generated_at,
            source=self.provider.name,
            quote_count=len(quotes),
            anomalies=tuple(anomalies),
            themes=tuple(themes),
        )
