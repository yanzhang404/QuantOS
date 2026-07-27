# QuantOS

QuantOS is an AI-native cryptocurrency quantitative research operating system.
Its long-term direction is to become the “Cursor for Quant Trading”: a workspace
where data, hypotheses, strategies, backtests, reviews, and experiment artifacts
form one reproducible research loop.

> QuantOS is a research platform, not a profit promise or an autonomous trading bot.

## Status

The project is in architecture design and V0.1 initialization. The current
milestone builds the repository foundation; paper and live trading are not
implemented.

## V0.1 capabilities

- Download public Binance historical Klines for BTCUSDT and ETHUSDT.
- Store 1h and 4h bars as versioned Parquet datasets.
- Query local datasets with DuckDB.
- Run an event-driven EMA cross example backtest.
- Model fees and fixed slippage.
- Produce returns, Sharpe ratio, maximum drawdown, trades, and an equity curve.
- Persist parameters, data versions, metrics, artifacts, and Markdown/HTML reports.

These capabilities describe the V0.1 target. Phase 0 currently provides the
architecture and delivery scaffold needed to implement them safely.

## Architecture at a glance

QuantOS starts as a modular monolith:

- **Go** owns platform-facing services such as APIs, orchestration, risk, and
  future execution control.
- **Python** owns market-data research, factor work, strategies, backtests,
  metrics, and experiment tools.
- **Parquet + DuckDB** provide the initial local analytical data plane.
- Shared schemas keep strategy, event, and experiment contracts explicit.

See [ARCHITECTURE.md](ARCHITECTURE.md) and the
[architecture decision records](docs/adr/README.md).

## Repository map

```text
apps/           Product entry points
services/       Domain modules within the modular monolith
packages/       Shared contracts and libraries
docs/           Product, architecture, and domain documentation
deployments/    Local deployment definitions
examples/       Reproducible research examples
scripts/        Development and validation utilities
tests/          Cross-module and acceptance tests
```

## Quick start

Phase 0 has no runtime service to start yet. Validate the repository foundation:

```bash
bash scripts/validate_structure.sh
```

Docker Compose is reserved for dependencies introduced by later phases:

```bash
docker compose config
```

## Roadmap

Delivery proceeds from a small reproducible research loop toward guarded
simulation and, only after explicit safety gates, live execution. See
[ROADMAP.md](ROADMAP.md) for milestone acceptance criteria.

## Safety

- Live trading is disabled and out of scope.
- Strategies emit signals; they never place exchange orders directly.
- Secrets and API keys must never be committed.
- AI actions must be backed by tool output and persisted artifacts.
- No component may enable live execution without explicit human authorization,
  risk controls, and a future architecture decision.

## License

Licensed under the [Apache License 2.0](LICENSE).
