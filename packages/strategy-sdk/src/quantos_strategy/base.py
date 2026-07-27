"""Minimal strategy lifecycle for backtest/paper/live consistency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quantos_events import FillEvent, MarketEvent, SignalEvent


@dataclass(frozen=True, slots=True)
class StrategyContext:
    symbol: str
    interval: str


class Strategy(Protocol):
    name: str
    version: str

    def initialize(self, context: StrategyContext) -> None: ...

    def on_bar(
        self,
        context: StrategyContext,
        event: MarketEvent,
    ) -> SignalEvent | None: ...

    def on_fill(self, context: StrategyContext, event: FillEvent) -> None: ...

    def finalize(self, context: StrategyContext) -> None: ...
