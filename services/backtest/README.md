# Backtest Service

Owns deterministic Kline replay, the V0.1 long-only risk policy, target-to-order
translation, fee/slippage fills, authoritative portfolio accounting, the EMA
Cross, funding-filtered EMA research strategies, and content-addressed
experiment artifacts.

It consumes immutable market-data versions and shared event/strategy/metric
contracts. It has no exchange adapter or live execution path.

`quantos backtest features` prints the versioned built-in feature registry.
Every new v4 experiment artifact resolves the selected strategy parameters into
feature instances and records their code symbol, inputs, warmup, current-bar
policy, semantic version, and definition SHA-256 in `run.json` and the report.
When a strategy consumes external features, the Run also binds the exact
materialized dataset manifest. The engine verifies one causal feature row per
selected Kline and feeds immutable observations through `MarketEvent`.
