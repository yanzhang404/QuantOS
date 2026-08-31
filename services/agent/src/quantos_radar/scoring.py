"""Versioned deterministic stock and theme heat scoring."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import MarketRadarInput, RadarStockInput

METHODOLOGY_VERSION = "quantos-market-radar-v1.0.0"
GENERATOR_VERSION = "0.1.0"
COMPONENT_WEIGHTS = {
    "price_move": 0.30,
    "relative_volume": 0.25,
    "turnover": 0.15,
    "momentum_30m": 0.20,
    "new_high_20d": 0.10,
}


def build_snapshot(
    radar: MarketRadarInput, baselines: Iterable[dict[str, Any]] = ()
) -> dict[str, Any]:
    baseline_list = list(baselines)
    stock_rows = [_score_stock(stock) for stock in radar.stocks]
    stock_rows.sort(key=lambda item: (-item["heat_score"], item["symbol"]))
    for rank, row in enumerate(stock_rows, 1):
        row["rank"] = rank
        row["acceleration_30m"] = _acceleration(
            baseline_list, radar.as_of, 30, "stocks", "symbol", row["symbol"], row["heat_score"]
        )
        row["acceleration_60m"] = _acceleration(
            baseline_list, radar.as_of, 60, "stocks", "symbol", row["symbol"], row["heat_score"]
        )
    theme_rows = _score_themes(stock_rows)
    for row in theme_rows:
        row["acceleration_30m"] = _acceleration(
            baseline_list, radar.as_of, 30, "themes", "name", row["name"], row["heat_score"]
        )
        row["acceleration_60m"] = _acceleration(
            baseline_list, radar.as_of, 60, "themes", "name", row["name"], row["heat_score"]
        )
    theme_rows.sort(key=lambda item: (-item["heat_score"], item["name"]))
    for rank, row in enumerate(theme_rows, 1):
        row["rank"] = rank
    rising = [item for item in theme_rows if item["acceleration_30m"] is not None]
    rising.sort(key=lambda item: (-item["acceleration_30m"], -item["heat_score"], item["name"]))
    payload = radar.to_dict()
    return {
        "schema_version": "1.0",
        "methodology_version": METHODOLOGY_VERSION,
        "market": radar.market,
        "as_of": payload["as_of"],
        "status": radar.status,
        "stocks": stock_rows,
        "themes": theme_rows,
        "summary": {
            "hottest_theme": theme_rows[0]["name"] if theme_rows else None,
            "fastest_rising_theme": rising[0]["name"] if rising else None,
            "leader_symbol": stock_rows[0]["symbol"] if stock_rows else None,
        },
        "provenance": {
            "input_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
            "generator_version": GENERATOR_VERSION,
            "provider": radar.provider,
            "stock_count": len(stock_rows),
            "theme_count": len(theme_rows),
        },
    }


def _score_stock(stock: RadarStockInput) -> dict[str, Any]:
    components: dict[str, float | None] = {
        "price_move": _clamp(stock.change_pct / 10 * 100),
        "relative_volume": (
            None if stock.relative_volume is None else _clamp((stock.relative_volume - 1) / 3 * 100)
        ),
        "turnover": (None if stock.turnover_pct is None else _clamp(stock.turnover_pct / 15 * 100)),
        "momentum_30m": (
            None if stock.change_30m_pct is None else _clamp(stock.change_30m_pct / 5 * 100)
        ),
        "new_high_20d": (
            None if stock.new_high_20d is None else (100.0 if stock.new_high_20d else 0.0)
        ),
    }
    coverage = sum(COMPONENT_WEIGHTS[key] for key, value in components.items() if value is not None)
    score = (
        sum(
            float(value) * COMPONENT_WEIGHTS[key]
            for key, value in components.items()
            if value is not None
        )
        / coverage
    )
    return {
        **stock.to_dict(),
        "rank": 0,
        "heat_score": _round(score),
        "data_coverage": _round(coverage),
        "heat_components": {
            key: None if value is None else _round(value) for key, value in components.items()
        },
        "acceleration_30m": None,
        "acceleration_60m": None,
    }


def _score_themes(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stock in stocks:
        for theme in stock["themes"]:
            members[theme].append(stock)
    rows: list[dict[str, Any]] = []
    for name, items in members.items():
        ordered = sorted(items, key=lambda item: (-item["heat_score"], item["symbol"]))
        leaders = ordered[:3]
        leader_score = sum(item["heat_score"] for item in leaders) / len(leaders)
        breadth_score = min(100.0, len(items) / 5 * 100)
        heat_score = leader_score * 0.70 + breadth_score * 0.30
        coverage = sum(item["data_coverage"] for item in items) / len(items)
        rows.append(
            {
                "rank": 0,
                "name": name,
                "heat_score": _round(heat_score),
                "leader_score": _round(leader_score),
                "breadth_score": _round(breadth_score),
                "data_coverage": _round(coverage),
                "observed_breadth": len(items),
                "leaders": [item["symbol"] for item in leaders],
                "acceleration_30m": None,
                "acceleration_60m": None,
            }
        )
    return rows


def _acceleration(
    baselines: list[dict[str, Any]],
    as_of: datetime,
    minutes: int,
    collection: str,
    key: str,
    value: str,
    score: float,
) -> float | None:
    target = as_of.astimezone(UTC) - timedelta(minutes=minutes)
    candidates: list[tuple[float, dict[str, Any]]] = []
    for snapshot in baselines:
        if snapshot.get("methodology_version") != METHODOLOGY_VERSION:
            continue
        try:
            baseline_at = _parse_datetime(snapshot.get("as_of"))
        except (TypeError, ValueError):
            continue
        distance = abs((baseline_at - target).total_seconds())
        if distance <= 15 * 60:
            candidates.append((distance, snapshot))
    if not candidates:
        return None
    baseline = min(candidates, key=lambda item: item[0])[1]
    items = baseline.get(collection)
    if not isinstance(items, list):
        return None
    match = next(
        (item for item in items if isinstance(item, dict) and item.get(key) == value),
        None,
    )
    if match is None or isinstance(match.get("heat_score"), bool):
        return None
    try:
        previous = float(match["heat_score"])
    except (KeyError, TypeError, ValueError):
        return None
    if not 0 <= previous <= 100:
        return None
    return _round(score - previous)


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError
    return parsed.astimezone(UTC)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _round(value: float) -> float:
    return round(value + 0.0, 2)


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
