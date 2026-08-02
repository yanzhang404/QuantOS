# Backtest Service

Owns deterministic Kline replay, the V0.1 long-only risk policy, target-to-order
translation, fee/slippage fills, authoritative portfolio accounting, the EMA
Cross example, and content-addressed experiment artifacts.

It consumes immutable market-data versions and shared event/strategy/metric
contracts. It has no exchange adapter or live execution path.

`quantos backtest features` prints the versioned built-in feature registry.
Every new v3 experiment artifact resolves the selected strategy parameters into
feature instances and records their code symbol, inputs, warmup, current-bar
policy, semantic version, and definition SHA-256 in `run.json` and the report.
