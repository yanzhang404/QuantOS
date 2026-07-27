"""Immutable event definitions for Kline-level backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class MarketEvent:
    timestamp: datetime
    exchange: str
    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True, slots=True)
class SignalEvent:
    timestamp: datetime
    symbol: str
    target_exposure: Decimal
    strategy: str
    reason: str


@dataclass(frozen=True, slots=True)
class RiskEvent:
    timestamp: datetime
    symbol: str
    requested_target: Decimal
    approved_target: Decimal
    approved: bool
    reason: str


@dataclass(frozen=True, slots=True)
class OrderEvent:
    timestamp: datetime
    symbol: str
    quantity: Decimal
    reference_price: Decimal
    reason: str


@dataclass(frozen=True, slots=True)
class FillEvent:
    timestamp: datetime
    symbol: str
    quantity: Decimal
    price: Decimal
    notional: Decimal
    fee: Decimal
    slippage_bps: Decimal
    reason: str


@dataclass(frozen=True, slots=True)
class PortfolioEvent:
    timestamp: datetime
    symbol: str
    cash: Decimal
    position_quantity: Decimal
    market_price: Decimal
    equity: Decimal


@dataclass(frozen=True, slots=True)
class MetricEvent:
    timestamp: datetime
    name: str
    value: float | int | None
