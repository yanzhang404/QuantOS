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
first formal Donchian ATR strategy study are now implemented. The current
increment includes a deterministic daily market-intelligence contract, bounded
public read-only collectors, empirical calibration history, read-only API, and
bilingual homepage view. New Runs now resolve built-in EMA, Donchian, and ATR
definitions from a versioned feature registry into their content identity.
The Go detail API validates those instances, and the Data/Strategies views make
the registry and selected Run lineage visible. Public Binance funding rates and
open-interest statistics now publish as separate immutable, content-verified
datasets with explicit source retention limits. A versioned closed-bar as-of
materializer binds exact Spot and derivatives inputs, preserves stale/missing
states, and rejects future observations. The engine now feeds those immutable
observations through `MarketEvent`; v4 Runs bind every consumed feature dataset,
and an initial funding-filtered EMA research strategy fails flat on stale or
missing inputs. The versioned API and workspace now expose that candidate's
specific parameters, accept only an immutable feature version rather than a
client path, verify its manifest against the selected Spot input, and show the
consumed v4 feature lineage in Run detail. Chronological selection and the four
robustness gates now run through bounded strategy-specific adapters for EMA
Cross and Donchian ATR; the funding-filtered external-feature strategy remains
to be brought through the same evidence path.
The workspace is split into Overview, Strategies, Runs, and Data views. A real
public Binance Spot bundle now versions BTCUSDT and ETHUSDT at 5m, 15m, 1h, 4h,
and 1d from 2021-01-01 through the latest complete UTC day. Current-data sync
extends the newest matching bundle without mutating prior evidence and records
real exchange maintenance gaps. Strategy submissions now bind and verify exact
bundle members, and each new immutable Run carries a bounded Kline projection
for synchronized price, fill, equity, and drawdown views. A Run catalog now
filters immutable experiment summaries, stores reversible archive markers
outside Run artifacts, and compares up to four normalized portfolio curves
with their exact inputs. Deterministic EMA and Donchian ATR robustness reviews
now link walk-forward, neighboring-parameter, doubled-cost, and aligned BTC/ETH
evidence through ordinary immutable Runs and expose promotion gates in the
workspace.
Candidate discovery now uses bounded Agent proposals and an atomic lifecycle
that separates implementation evidence, strategy-matched robustness reviews,
and explicit human decisions. The Go API and Overview queue expose these
records read-only. A UTC ISO-week scheduler now prepares at most two narrow,
explainable candidate review packages, exposes their occupied slots read-only,
and performs no remote GitHub mutation. Daily intelligence now collects seven
source-linked factors and bounded headline metadata from explicitly allow-listed
public endpoints, atomically pins the first UTC daily batch, and remains partial
until 30 observations calibrate its percentiles. A single-writer refresh job,
persistent daily timer, and read-only last-success/staleness health now make the
publication boundary observable without adding startup network calls. A
deterministic A-share Market Radar now publishes immutable ten-minute stock and
theme heat snapshots with 30/60-minute acceleration, a read-only API, and a
bilingual overview. Missing RVOL, turnover, momentum, or new-high inputs remain
visible as partial coverage rather than being estimated. The canonical Go/Python
research service now has
a production container, environment contract, and data-aware readiness check;
provisioning a stateful container host and connecting its stable HTTPS URL
remain before the workspace can drop its localhost dependency. Paper
reproduction remains a later research workflow.

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
