"""Built-in research strategies."""

from __future__ import annotations

from decimal import Decimal

from quantos_events import FillEvent, MarketEvent, SignalEvent
from quantos_strategy import StrategyContext

from .errors import BacktestConfigurationError


class EmaCrossStrategy:
    name = "ema-cross"
    version = "1.0.0"

    def __init__(self, *, fast_period: int, slow_period: int) -> None:
        if fast_period < 1 or slow_period < 2 or fast_period >= slow_period:
            raise BacktestConfigurationError(
                "EMA periods must satisfy 1 <= fast_period < slow_period"
            )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self._fast_alpha = Decimal("2") / Decimal(fast_period + 1)
        self._slow_alpha = Decimal("2") / Decimal(slow_period + 1)
        self._fast_ema: Decimal | None = None
        self._slow_ema: Decimal | None = None
        self._observations = 0
        self._target = Decimal("0")

    @property
    def parameters(self) -> dict[str, int]:
        return {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
        }

    def initialize(self, context: StrategyContext) -> None:
        self._fast_ema = None
        self._slow_ema = None
        self._observations = 0
        self._target = Decimal("0")

    def on_bar(
        self,
        context: StrategyContext,
        event: MarketEvent,
    ) -> SignalEvent | None:
        self._observations += 1
        self._fast_ema = self._update(self._fast_ema, event.close, self._fast_alpha)
        self._slow_ema = self._update(self._slow_ema, event.close, self._slow_alpha)
        if self._observations < self.slow_period:
            return None

        target = Decimal("1") if self._fast_ema > self._slow_ema else Decimal("0")
        if target == self._target:
            return None
        self._target = target
        return SignalEvent(
            timestamp=event.close_time,
            symbol=context.symbol,
            target_exposure=target,
            strategy=self.name,
            reason=(
                f"EMA({self.fast_period}) {'above' if target else 'not above'} "
                f"EMA({self.slow_period})"
            ),
        )

    def on_fill(self, context: StrategyContext, event: FillEvent) -> None:
        return None

    def finalize(self, context: StrategyContext) -> None:
        return None

    @staticmethod
    def _update(current: Decimal | None, value: Decimal, alpha: Decimal) -> Decimal:
        return value if current is None else alpha * value + (Decimal("1") - alpha) * current
