# Project Context

## Mission

QuantOS is an AI-native crypto quantitative research operating system. It
prioritizes a correct, reproducible, and extensible research workflow over
short-term trading automation.

## Current phase

Phase 0 architecture initialization is complete. The implemented loop now
covers Binance Kline → validation → Parquet → DuckDB → event-driven EMA Cross
backtest → metrics → versioned experiment artifacts → chronological parameter
selection → untouched holdout and cost-stress review. Buy and Hold plus the
first formal Donchian ATR strategy study are now implemented. The next
increment also includes a deterministic daily market-intelligence contract,
read-only API, and bilingual homepage view. Current data collection still
requires a bounded external Agent/OpenClaw adapter; strategy robustness,
feature lineage, walk-forward validation, and broader market datasets remain.
The workspace is split into Overview, Strategies, Runs, and Data views. A real
public Binance Spot bundle now versions BTCUSDT and ETHUSDT at 5m, 15m, 1h, 4h,
and 1d from 2021-01-01 through the latest complete UTC day. Current-data sync
extends the newest matching bundle without mutating prior evidence and records
real exchange maintenance gaps. Strategy submissions now bind and verify exact
bundle members, and each new immutable Run carries a bounded Kline projection
for synchronized price, fill, equity, and drawdown views. A Run catalog now
filters immutable experiment summaries, stores reversible archive markers
outside Run artifacts, and compares up to four normalized portfolio curves
with their exact inputs. The next boundary is robustness gates before richer
Agent candidate workflows. The canonical Go/Python research service now has a production
container, environment contract, and data-aware readiness check; provisioning a
stateful container host and connecting its stable HTTPS URL remain before the
workspace can drop its localhost dependency. Paper reproduction remains a later
research workflow.

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
