# Roadmap

Each milestone must leave the repository runnable, documented, and reproducible.
Dates are intentionally omitted until implementation capacity is known.

## V0.1 — Reproducible research loop

Implementation status: the core vertical slice is complete; broader validation
and release hardening remain.

- Complete Phase 0 repository, CI, and local development foundation.
- Download Binance BTCUSDT/ETHUSDT Klines at 1h and 4h.
- Validate and persist versioned Parquet datasets.
- Query datasets with DuckDB.
- Implement the strategy/event contracts and an EMA cross example.
- Run a deterministic Kline-level event-driven backtest.
- Apply fees and fixed slippage.
- Calculate returns, Sharpe ratio, maximum drawdown, trades, and equity curve.
- Persist experiment inputs, versions, metrics, artifacts, and reports.
- Establish Buy & Hold and Donchian ATR as the first formal strategy benchmarks.

Exit criterion: a clean environment can reproduce one documented experiment
from data download through report generation.

## V0.2 — Research quality and review

- Feature registry and dataset lineage.
- Parameter sweeps and train/validation/out-of-sample splits. **Implemented.**
- Funding-rate and open-interest datasets.
- Bias, leakage, and sensitivity review checks. **Initial automated checks implemented.**
- Richer experiment comparison and artifact browsing. **JSON comparison implemented.**

Exit criterion: researchers can compare runs and identify common validity risks.

## V0.3 — Product workspace

- Dashboard and project navigation. **Top navigation, Research Center, result-first workspace, and folder-style Strategy Library implemented.**
- Dataset, strategy, backtest, and experiment views. **Interactive parameter submission, Task history, and dynamic Experiment detail implemented; comparison pending.**
- Task orchestration and progress streaming. **Local durable task API and worker implemented; streaming pending.**
- Tool-driven AI research assistant for querying and reviewing artifacts.
- Daily source-linked market brief and deterministic sentiment index. **Initial contract, local publisher, read-only API, and homepage view implemented.**
- Manifest-driven strategy parameters and candidate-to-promotion lifecycle. **Initial catalog and evidence view implemented.**
- Multi-timeframe research datasets. **BTC/ETH 5m/15m/1h/4h/1d immutable bundle, 2021-to-current coverage evidence, incremental sync, verified backtest member resolution, and Run Kline projections implemented.**
- Hosted canonical research service. **Deployment contract, production image, environment configuration, and data-aware readiness implemented; external host provisioning remains.**
- Result-first product information architecture. **Overview, Strategies, Runs,
  and Data views accepted; initial workspace split in progress.**

The accepted delivery order for the remaining V0.3 work is:

1. split and simplify the four product views; **Implemented.**
2. load immutable BTC/ETH datasets for 5m, 15m, 1h, 4h, and 1d; **Implemented from 2021-01-01 through the latest complete UTC day, with immutable incremental refresh.**
3. add immutable Run filtering, archival, and up-to-four comparison; **Implemented.**
4. add walk-forward, neighboring-parameter, doubled-cost, and multi-market gates; **Implemented for the EMA research workflow.**
5. add candidate strategy lifecycle and bounded Agent proposal contracts;
6. schedule at most one or two explainable candidates per week through draft PRs;
7. replace the sample intelligence input with public, read-only daily collectors.

Exit criterion: the core research loop is usable without manually coordinating
individual command-line steps.

## Paper Trading

- Real-time public market-data ingestion.
- Simulated accounts, fills, and portfolio accounting.
- Operational risk limits, monitoring, alerts, and kill switch.
- Backtest/paper behavior comparison and reconciliation.

Entry gate: V0.3 contracts and deterministic accounting are stable.

## Live Trading

- Secure secret storage and least-privilege credentials.
- Idempotent order management and REST/WebSocket reconciliation.
- Exchange fault handling, audit trails, and human approval controls.
- Staged deployment with strict capital and risk limits.

Entry gate: paper trading has sustained validation, an explicit ADR approves the
design, and a human operator deliberately enables execution.

## Long-term AI Research Team

Introduce tool-constrained Researcher, Engineer, Backtest, Reviewer, and Risk
Officer roles. Agents may propose and evaluate work, but cannot bypass review,
risk policy, or live-trading authorization.
