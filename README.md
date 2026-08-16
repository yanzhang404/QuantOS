# QuantOS

QuantOS is an AI-native quantitative research operating system.
Its long-term direction is to become the “Cursor for Quant Trading”: a workspace
where data, hypotheses, strategies, backtests, reviews, and experiment artifacts
form one reproducible research loop.

> QuantOS is a research platform, not a profit promise or an autonomous trading bot.

## Status

The Phase 0 foundation now has runnable read-only A-share and US market-radar
workflows. The original Binance research loop remains a V0.1 target; paper and
live trading are not implemented.

## V0.1 target capabilities

- Download public Binance historical Klines for BTCUSDT and ETHUSDT.
- Store 1h and 4h bars as versioned Parquet datasets.
- Query local datasets with DuckDB.
- Run an event-driven EMA cross example backtest.
- Model fees and fixed slippage.
- Produce returns, Sharpe ratio, maximum drawdown, trades, and an equity curve.
- Persist parameters, data versions, metrics, artifacts, and Markdown/HTML reports.

These capabilities describe the V0.1 target. Phase 0 currently provides the
architecture and delivery scaffold needed to implement them safely.

An additional read-only A-share Market Radar v0.1 is implemented under
`services/market-data`. It provides full-market quote acquisition, stock anomaly
detection, theme heat and acceleration ranking, and a worker CLI. It does not
place orders or enable live trading. See
[`services/market-data/README.md`](services/market-data/README.md).

The same module now includes a two-stage US intraday-options research funnel:
live or replayed equity heat first, then bounded option-chain snapshots with
spread, freshness, volume, open-interest, and contract tradability checks. It
persists evidence and supports console/Slack/WeCom webhook notifications.

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

Install the market-data package, validate the repository, and run the US replay:

```bash
python -m pip install -e services/market-data
bash scripts/validate_structure.sh
python -m unittest discover -s services/market-data/tests -v
quantos-us-radar replay --input examples/us-market-radar/bars.jsonl \
  --option-chain examples/us-market-radar/option-chain.json --min-score 35
```

The live read-only worker is an opt-in Compose profile and requires local
credentials plus an entitled market-data feed:

```bash
docker compose --profile us-radar up --build -d us-market-radar
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
