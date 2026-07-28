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

- Dashboard and project navigation.
- Dataset, strategy, backtest, and experiment views.
- Task orchestration and progress streaming.
- Tool-driven AI research assistant for querying and reviewing artifacts.

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
