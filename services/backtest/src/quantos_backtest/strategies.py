"""Built-in research strategies."""

from __future__ import annotations

from collections import deque
from decimal import ROUND_DOWN, Decimal, localcontext

from quantos_events import FillEvent, MarketEvent, SignalEvent
from quantos_strategy import StrategyContext

from .errors import BacktestConfigurationError

PERIODS_PER_YEAR = {
    "5m": 365 * 24 * 12,
    "15m": 365 * 24 * 4,
    "1h": 365 * 24,
    "4h": 365 * 6,
    "1d": 365,
}


class BuyAndHoldStrategy:
    """Invest once after the first observed close and hold until the run ends."""

    name = "buy-and-hold"
    version = "1.0.0"

    def __init__(self, *, target_exposure: Decimal = Decimal("1")) -> None:
        if not Decimal("0") < target_exposure <= Decimal("1"):
            raise BacktestConfigurationError("target_exposure must be in (0, 1]")
        self.target_exposure = target_exposure
        self._invested = False

    @property
    def parameters(self) -> dict[str, str]:
        return {"target_exposure": str(self.target_exposure)}

    def initialize(self, context: StrategyContext) -> None:
        self._invested = False

    def on_bar(
        self,
        context: StrategyContext,
        event: MarketEvent,
    ) -> SignalEvent | None:
        if self._invested:
            return None
        self._invested = True
        return SignalEvent(
            timestamp=event.close_time,
            symbol=context.symbol,
            target_exposure=self.target_exposure,
            strategy=self.name,
            reason="establish buy-and-hold benchmark exposure",
        )

    def on_fill(self, context: StrategyContext, event: FillEvent) -> None:
        return None

    def finalize(self, context: StrategyContext) -> None:
        return None


class DonchianAtrStrategy:
    """Long-only channel breakout with ATR-based volatility targeting."""

    name = "donchian-atr"
    version = "1.0.0"

    def __init__(
        self,
        *,
        entry_period: int = 20,
        exit_period: int = 10,
        atr_period: int = 20,
        target_annual_volatility: Decimal = Decimal("0.20"),
        max_exposure: Decimal = Decimal("1"),
        rebalance_threshold: Decimal = Decimal("0.05"),
    ) -> None:
        if entry_period < 2:
            raise BacktestConfigurationError("entry_period must be at least 2")
        if exit_period < 1 or exit_period > entry_period:
            raise BacktestConfigurationError("exit_period must be in [1, entry_period]")
        if atr_period < 2:
            raise BacktestConfigurationError("atr_period must be at least 2")
        if target_annual_volatility <= 0:
            raise BacktestConfigurationError("target_annual_volatility must be positive")
        if not Decimal("0") < max_exposure <= Decimal("1"):
            raise BacktestConfigurationError("max_exposure must be in (0, 1]")
        if not Decimal("0") <= rebalance_threshold <= Decimal("1"):
            raise BacktestConfigurationError("rebalance_threshold must be in [0, 1]")
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.target_annual_volatility = target_annual_volatility
        self.max_exposure = max_exposure
        self.rebalance_threshold = rebalance_threshold
        self._highs: deque[Decimal] = deque(maxlen=entry_period)
        self._lows: deque[Decimal] = deque(maxlen=exit_period)
        self._true_ranges: deque[Decimal] = deque(maxlen=atr_period)
        self._previous_close: Decimal | None = None
        self._target = Decimal("0")

    @property
    def parameters(self) -> dict[str, int | str]:
        return {
            "entry_period": self.entry_period,
            "exit_period": self.exit_period,
            "atr_period": self.atr_period,
            "target_annual_volatility": str(self.target_annual_volatility),
            "max_exposure": str(self.max_exposure),
            "rebalance_threshold": str(self.rebalance_threshold),
        }

    def initialize(self, context: StrategyContext) -> None:
        self._highs.clear()
        self._lows.clear()
        self._true_ranges.clear()
        self._previous_close = None
        self._target = Decimal("0")

    def on_bar(
        self,
        context: StrategyContext,
        event: MarketEvent,
    ) -> SignalEvent | None:
        true_range = self._true_range(event)
        historical_entry = max(self._highs) if len(self._highs) == self.entry_period else None
        historical_exit = min(self._lows) if len(self._lows) == self.exit_period else None
        atr_values = [*self._true_ranges, true_range]
        atr = (
            sum(atr_values[-self.atr_period :], start=Decimal("0")) / Decimal(self.atr_period)
            if len(atr_values) >= self.atr_period
            else None
        )

        next_target = self._target
        reason: str | None = None
        if (
            self._target == 0
            and historical_entry is not None
            and atr is not None
            and event.close > historical_entry
        ):
            next_target = self._volatility_target(event, atr)
            reason = (
                f"close {event.close} broke above prior {self.entry_period}-bar "
                f"high {historical_entry}"
            )
        elif self._target > 0 and historical_exit is not None and event.close < historical_exit:
            next_target = Decimal("0")
            reason = (
                f"close {event.close} broke below prior {self.exit_period}-bar "
                f"low {historical_exit}"
            )
        elif self._target > 0 and atr is not None:
            volatility_target = self._volatility_target(event, atr)
            if abs(volatility_target - self._target) >= self.rebalance_threshold:
                next_target = volatility_target
                reason = "rebalance to ATR volatility target"

        self._highs.append(event.high)
        self._lows.append(event.low)
        self._true_ranges.append(true_range)
        self._previous_close = event.close
        if reason is None or next_target == self._target:
            return None
        self._target = next_target
        return SignalEvent(
            timestamp=event.close_time,
            symbol=context.symbol,
            target_exposure=next_target,
            strategy=self.name,
            reason=reason,
        )

    def on_fill(self, context: StrategyContext, event: FillEvent) -> None:
        return None

    def finalize(self, context: StrategyContext) -> None:
        return None

    def _true_range(self, event: MarketEvent) -> Decimal:
        if self._previous_close is None:
            return event.high - event.low
        return max(
            event.high - event.low,
            abs(event.high - self._previous_close),
            abs(event.low - self._previous_close),
        )

    def _volatility_target(
        self,
        event: MarketEvent,
        atr: Decimal | None,
    ) -> Decimal:
        if atr is None or atr <= 0 or event.close <= 0:
            return self.max_exposure
        try:
            periods = PERIODS_PER_YEAR[event.interval]
        except KeyError as exc:
            raise BacktestConfigurationError(
                f"unsupported interval for volatility targeting: {event.interval}"
            ) from exc
        with localcontext() as context:
            context.prec = 28
            annualized_atr = atr / event.close * Decimal(periods).sqrt()
            target = min(self.max_exposure, self.target_annual_volatility / annualized_atr)
            return target.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)


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


class FundingFilteredEmaStrategy(EmaCrossStrategy):
    """EMA trend strategy that fails flat when causal funding is high or unavailable."""

    name = "funding-filtered-ema"
    version = "0.1.0"

    def __init__(
        self,
        *,
        fast_period: int,
        slow_period: int,
        max_funding_rate: Decimal = Decimal("0.0001"),
    ) -> None:
        super().__init__(fast_period=fast_period, slow_period=slow_period)
        if not max_funding_rate.is_finite() or abs(max_funding_rate) > Decimal("0.01"):
            raise BacktestConfigurationError(
                "max_funding_rate must be finite and within [-0.01, 0.01]"
            )
        self.max_funding_rate = max_funding_rate

    @property
    def parameters(self) -> dict[str, int | str]:
        return {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "max_funding_rate": str(self.max_funding_rate),
        }

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

        funding = next(
            (item for item in event.features if item.feature_id == "aligned-funding-rate"),
            None,
        )
        funding_rate = None
        if funding is not None and funding.availability == "matched":
            funding_rate = dict(funding.values).get("funding_rate")
        trend_is_long = self._fast_ema > self._slow_ema
        funding_permits_long = funding_rate is not None and funding_rate <= self.max_funding_rate
        target = Decimal("1") if trend_is_long and funding_permits_long else Decimal("0")
        if target == self._target:
            return None
        self._target = target
        if target:
            reason = (
                f"EMA({self.fast_period}) above EMA({self.slow_period}); "
                f"funding {funding_rate} <= {self.max_funding_rate}"
            )
        elif funding_rate is None:
            reason = "funding unavailable or stale; fail flat"
        elif funding_rate > self.max_funding_rate:
            reason = f"funding {funding_rate} above {self.max_funding_rate}; exit crowded long"
        else:
            reason = f"EMA({self.fast_period}) not above EMA({self.slow_period})"
        return SignalEvent(
            timestamp=event.close_time,
            symbol=context.symbol,
            target_exposure=target,
            strategy=self.name,
            reason=reason,
        )
