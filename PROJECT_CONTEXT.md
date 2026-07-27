# Project Context

## Mission

QuantOS is an AI-native crypto quantitative research operating system. It
prioritizes a correct, reproducible, and extensible research workflow over
short-term trading automation.

## Current phase

Phase 0 architecture initialization is complete. The V0.1 core loop now covers
Binance Kline → validation → Parquet → DuckDB → event-driven EMA Cross backtest
→ metrics → versioned experiment artifacts and Markdown report. The next
increment is research-quality review and broader validation.

## Product principles

1. **Research first** — prove the research loop before connecting execution.
2. **Everything versioned** — data, features, strategies, parameters, engine
   logic, metrics, prompts, and results must be attributable.
3. **Everything reproducible** — a run must identify all inputs needed to repeat it.
4. **Backtest/live consistency** — future simulation and execution reuse domain
   contracts, but live trading remains disabled.
5. **Signals before orders** — strategies express intent; risk and execution
   components own authorization and order state.
6. **Tool-grounded AI** — claims about experiments require queries, executions,
   and stored artifacts.
7. **Safe by default** — no plaintext secrets, unlimited positions, bypassed
   controls, or autonomous live activation.
8. **Modular monolith first** — split deployment units only when stable domain
   boundaries and operational evidence justify it.

## V0.1 scope

In scope:

- Binance public historical Klines
- BTCUSDT and ETHUSDT
- 1h and 4h intervals
- Parquet storage and DuckDB queries
- EMA trend strategy
- Kline-level event-driven backtesting
- Fees and fixed slippage
- Core performance metrics and trade/equity artifacts
- Experiment metadata and Markdown/HTML reports
- Local Docker Compose, tests, documentation, and CI

Out of scope:

- Tick/HFT simulation and full order-book modeling
- Multi-exchange arbitrage
- Paper or live trading
- Autonomous management of real funds
- Kubernetes, microservices, multi-tenant SaaS, and marketplaces

## Reproducibility contract

Every experiment run will eventually record:

- hypothesis and project identity
- immutable dataset version
- feature and strategy versions
- parameters and configuration
- backtest engine and metrics versions
- status, metrics, artifacts, and report locations

## Ownership

Yan is the project owner. Optimize for a single maintainer or small team:
explicit boundaries, incremental delivery, strong documentation, and safe AI
collaboration.
