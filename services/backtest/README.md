# Backtest Service

Owns deterministic Kline replay, the V0.1 long-only risk policy, target-to-order
translation, fee/slippage fills, authoritative portfolio accounting, the EMA
Cross example, and content-addressed experiment artifacts.

It consumes immutable market-data versions and shared event/strategy/metric
contracts. It has no exchange adapter or live execution path.
