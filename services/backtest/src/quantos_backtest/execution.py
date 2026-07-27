"""Deterministic order sizing, fixed slippage, and proportional fees."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from quantos_events import FillEvent, OrderEvent, RiskEvent

from .portfolio import Portfolio

BASIS_POINTS = Decimal("10000")
QUANTITY_QUANTUM = Decimal("0.000000000001")


class ExecutionModel:
    def __init__(self, *, fee_bps: Decimal, slippage_bps: Decimal) -> None:
        self.fee_rate = fee_bps / BASIS_POINTS
        self.slippage_bps = slippage_bps
        self.slippage_rate = slippage_bps / BASIS_POINTS

    def preview_price(self, reference_price: Decimal, quantity: Decimal) -> Decimal:
        direction = Decimal("1") if quantity > 0 else Decimal("-1")
        return reference_price * (Decimal("1") + direction * self.slippage_rate)

    def fill(self, order: OrderEvent) -> FillEvent:
        price = self.preview_price(order.reference_price, order.quantity)
        notional = abs(order.quantity * price)
        return FillEvent(
            timestamp=order.timestamp,
            symbol=order.symbol,
            quantity=order.quantity,
            price=price,
            notional=notional,
            fee=notional * self.fee_rate,
            slippage_bps=self.slippage_bps,
            reason=order.reason,
        )


class TargetOrderManager:
    """Translate approved target exposure into one market order."""

    def create_order(
        self,
        risk: RiskEvent,
        *,
        timestamp: datetime,
        reference_price: Decimal,
        portfolio: Portfolio,
        execution: ExecutionModel,
    ) -> OrderEvent | None:
        if not risk.approved:
            return None

        equity = portfolio.equity(reference_price)
        provisional_target = equity * risk.approved_target / reference_price
        provisional_delta = provisional_target - portfolio.position_quantity
        if provisional_delta == 0:
            return None

        fill_price = execution.preview_price(reference_price, provisional_delta)
        desired_quantity = equity * risk.approved_target / fill_price
        quantity = desired_quantity - portfolio.position_quantity

        if quantity > 0:
            affordable = portfolio.cash / (fill_price * (Decimal("1") + execution.fee_rate))
            quantity = min(quantity, affordable)
        else:
            quantity = max(quantity, -portfolio.position_quantity)

        quantity = quantity.quantize(QUANTITY_QUANTUM, rounding=ROUND_DOWN)
        if quantity == 0:
            return None
        return OrderEvent(
            timestamp=timestamp,
            symbol=portfolio.symbol,
            quantity=quantity,
            reference_price=reference_price,
            reason=f"rebalance to target exposure {risk.approved_target}",
        )
