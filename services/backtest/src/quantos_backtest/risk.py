"""Long-only risk policy for the V0.1 research engine."""

from __future__ import annotations

from decimal import Decimal

from quantos_events import RiskEvent, SignalEvent


class LongOnlyRiskEngine:
    def __init__(self, *, max_target_exposure: Decimal) -> None:
        self.max_target_exposure = max_target_exposure

    def evaluate(self, signal: SignalEvent, *, symbol: str) -> RiskEvent:
        approved = (
            signal.symbol == symbol
            and Decimal("0") <= signal.target_exposure <= self.max_target_exposure
        )
        return RiskEvent(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            requested_target=signal.target_exposure,
            approved_target=signal.target_exposure if approved else Decimal("0"),
            approved=approved,
            reason=(
                "approved by long-only exposure limit" if approved else "rejected by risk policy"
            ),
        )
