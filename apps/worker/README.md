# Worker App

Composition root for long-running and replayable market-data workers. Future
backtest and experiment tasks must keep their contracts reproducible and
idempotent.

`market_radar.py` is the local composition root for A-share Market Radar v0.1.
It delegates to the installed `quantos-market-data` package and supports live
read-only acquisition or recorded JSON replay.

`us_market_radar.py` runs the US equity heat stage. It supports Alpaca live
minute bars, deterministic JSON Lines replay, JSON Lines report persistence,
console summaries, and Slack/WeCom/generic webhook delivery. It is observational
only and contains no brokerage or order-management client. Optional option-chain
enrichment checks liquidity and risk for only the top underlying candidates.
