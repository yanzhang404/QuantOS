"""Evidence-backed forward outcome review for saved US radar alerts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from .us_models import USEquityBar


@dataclass(frozen=True)
class SignalOutcome:
    symbol: str
    alerted_at: datetime
    direction: str
    entry_price: float
    horizon_minutes: int
    complete: bool
    observed_at: datetime | None
    raw_return_pct: float | None
    directional_return_pct: float | None
    max_favorable_excursion_pct: float | None
    max_adverse_excursion_pct: float | None


@dataclass(frozen=True)
class HorizonSummary:
    horizon_minutes: int
    complete_count: int
    positive_count: int
    hit_rate: float | None
    mean_directional_return_pct: float | None
    mean_max_favorable_excursion_pct: float | None
    mean_max_adverse_excursion_pct: float | None


@dataclass(frozen=True)
class RadarEvaluationReport:
    schema_version: str
    evaluated_at: datetime
    alert_count: int
    outcomes: tuple[SignalOutcome, ...]
    summaries: tuple[HorizonSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evaluated_at"] = self.evaluated_at.isoformat()
        for outcome in value["outcomes"]:
            outcome["alerted_at"] = outcome["alerted_at"].isoformat()
            if outcome["observed_at"] is not None:
                outcome["observed_at"] = outcome["observed_at"].isoformat()
        return value


@dataclass(frozen=True)
class _Alert:
    symbol: str
    timestamp: datetime
    direction: str
    entry_price: float


class RadarOutcomeEvaluator:
    def __init__(self, horizons: Sequence[int] = (5, 15, 30)) -> None:
        normalized = tuple(sorted(set(int(item) for item in horizons)))
        if not normalized or any(item <= 0 for item in normalized):
            raise ValueError("evaluation horizons must be positive minutes")
        self.horizons = normalized

    def evaluate_files(
        self, reports_path: str | Path, bars_path: str | Path
    ) -> RadarEvaluationReport:
        alerts = self._load_alerts(Path(reports_path))
        bars = self._load_bars(Path(bars_path))
        return self.evaluate(alerts, bars)

    def evaluate(
        self, alerts: Sequence[_Alert], bars: Sequence[USEquityBar]
    ) -> RadarEvaluationReport:
        by_symbol: dict[str, list[USEquityBar]] = {}
        for bar in bars:
            by_symbol.setdefault(bar.symbol, []).append(bar)
        for values in by_symbol.values():
            values.sort(key=lambda item: item.timestamp)
        outcomes = tuple(
            self._outcome(alert, horizon, by_symbol.get(alert.symbol, []))
            for alert in alerts
            for horizon in self.horizons
        )
        summaries = tuple(self._summary(horizon, outcomes) for horizon in self.horizons)
        return RadarEvaluationReport(
            schema_version="us-radar-evaluation/v0.1",
            evaluated_at=datetime.now(timezone.utc),
            alert_count=len(alerts),
            outcomes=outcomes,
            summaries=summaries,
        )

    def _outcome(
        self, alert: _Alert, horizon: int, bars: Sequence[USEquityBar]
    ) -> SignalOutcome:
        target = alert.timestamp + timedelta(minutes=horizon)
        future = [item for item in bars if alert.timestamp < item.timestamp <= target]
        observed = next((item for item in bars if item.timestamp == target), None)
        if observed is None:
            return SignalOutcome(
                symbol=alert.symbol, alerted_at=alert.timestamp,
                direction=alert.direction, entry_price=alert.entry_price,
                horizon_minutes=horizon, complete=False, observed_at=None,
                raw_return_pct=None, directional_return_pct=None,
                max_favorable_excursion_pct=None, max_adverse_excursion_pct=None,
            )
        raw_return = (observed.close / alert.entry_price - 1.0) * 100.0
        high_return = (max(item.high for item in future) / alert.entry_price - 1.0) * 100.0
        low_return = (min(item.low for item in future) / alert.entry_price - 1.0) * 100.0
        if alert.direction == "down":
            directional = -raw_return
            favorable = -low_return
            adverse = -high_return
        elif alert.direction == "up":
            directional = raw_return
            favorable = high_return
            adverse = low_return
        else:
            directional = 0.0
            favorable = max(abs(high_return), abs(low_return))
            adverse = min(high_return, low_return)
        return SignalOutcome(
            symbol=alert.symbol, alerted_at=alert.timestamp,
            direction=alert.direction, entry_price=alert.entry_price,
            horizon_minutes=horizon, complete=True,
            observed_at=observed.timestamp,
            raw_return_pct=round(raw_return, 4),
            directional_return_pct=round(directional, 4),
            max_favorable_excursion_pct=round(favorable, 4),
            max_adverse_excursion_pct=round(adverse, 4),
        )

    @staticmethod
    def _summary(horizon: int, outcomes: Sequence[SignalOutcome]) -> HorizonSummary:
        complete = [item for item in outcomes
                    if item.horizon_minutes == horizon and item.complete]
        if not complete:
            return HorizonSummary(horizon, 0, 0, None, None, None, None)
        positive = sum((item.directional_return_pct or 0) > 0 for item in complete)

        def mean(field: str) -> float:
            return round(sum(float(getattr(item, field)) for item in complete) / len(complete), 4)

        return HorizonSummary(
            horizon_minutes=horizon,
            complete_count=len(complete),
            positive_count=positive,
            hit_rate=round(positive / len(complete), 4),
            mean_directional_return_pct=mean("directional_return_pct"),
            mean_max_favorable_excursion_pct=mean("max_favorable_excursion_pct"),
            mean_max_adverse_excursion_pct=mean("max_adverse_excursion_pct"),
        )

    @staticmethod
    def _load_alerts(path: Path) -> list[_Alert]:
        alerts: list[_Alert] = []
        seen: set[tuple[str, datetime]] = set()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            timestamp = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError(f"report timestamp at line {line_number} must be timezone-aware")
            schema = payload.get("schema_version")
            if schema == "us-equity-heat/v0.1":
                rows = [
                    (item["symbol"], item["direction"], item["price"])
                    for item in payload.get("candidates", [])
                ]
            elif schema == "us-options-radar/v0.1":
                rows = [
                    (item["symbol"], item["direction"], item["underlying_price"])
                    for item in payload.get("underlyings", [])
                ]
            else:
                raise ValueError(f"unsupported report schema at line {line_number}: {schema}")
            for symbol, direction, price in rows:
                key = (str(symbol), timestamp)
                if key not in seen:
                    seen.add(key)
                    alerts.append(_Alert(str(symbol), timestamp, str(direction), float(price)))
        return alerts

    @staticmethod
    def _load_bars(path: Path) -> list[USEquityBar]:
        result: list[USEquityBar] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            messages = payload if isinstance(payload, list) else [payload]
            for item in messages:
                if item.get("T") not in (None, "b", "u"):
                    continue
                try:
                    result.append(USEquityBar.from_dict(item))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"invalid outcome bar at line {line_number}: {exc}") from exc
        return result
