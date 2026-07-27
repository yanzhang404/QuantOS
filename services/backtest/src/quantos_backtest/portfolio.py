"""Authoritative simulated cash and position accounting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from quantos_events import FillEvent, PortfolioEvent

from .errors import PortfolioError

ZERO = Decimal("0")
EPSILON = Decimal("0.00000001")


class Portfolio:
    def __init__(self, *, symbol: str, initial_cash: Decimal) -> None:
        self.symbol = symbol
        self.cash = initial_cash
        self.position_quantity = ZERO
        self.fees_paid = ZERO

    def equity(self, market_price: Decimal) -> Decimal:
        return self.cash + self.position_quantity * market_price

    def apply_fill(self, fill: FillEvent) -> None:
        if fill.symbol != self.symbol:
            raise PortfolioError("fill symbol does not match portfolio")
        next_position = self.position_quantity + fill.quantity
        next_cash = self.cash - fill.quantity * fill.price - fill.fee
        if next_position < -EPSILON:
            raise PortfolioError("long-only portfolio cannot become short")
        if next_cash < -EPSILON:
            raise PortfolioError("fill would make cash negative")
        self.position_quantity = max(ZERO, next_position)
        self.cash = max(ZERO, next_cash)
        self.fees_paid += fill.fee

    def snapshot(self, *, timestamp: datetime, market_price: Decimal) -> PortfolioEvent:
        return PortfolioEvent(
            timestamp=timestamp,
            symbol=self.symbol,
            cash=self.cash,
            position_quantity=self.position_quantity,
            market_price=market_price,
            equity=self.equity(market_price),
        )
