# QuantOS

QuantOS is an AI-native cryptocurrency quantitative research operating system.
Its long-term direction is to become the “Cursor for Quant Trading”: a workspace
where data, hypotheses, strategies, backtests, reviews, and experiment artifacts
form one reproducible research loop.

> QuantOS is a research platform, not a profit promise or an autonomous trading bot.

## Status

The V0.1 core loop and the first V0.2 research-quality slice are available.
Paper and live trading are not implemented.

## V0.1 capabilities

- Download public Binance historical Klines for BTCUSDT and ETHUSDT.
- Store 5m, 15m, 1h, 4h, and 1d bars as versioned Parquet datasets.
- Version the complete BTC/ETH interval matrix as one immutable dataset bundle.
- Query local datasets with DuckDB.
- Run an event-driven EMA cross example backtest.
- Model fees and fixed slippage.
- Produce returns, Sharpe ratio, maximum drawdown, trades, and an equity curve.
- Persist parameters, data versions, metrics, artifacts, and Markdown/HTML reports.
- Select EMA parameters with chronological train/validation/test splits.
- Evaluate only the validation winner on an untouched holdout and doubled costs.
- Compare experiment runs and generate automated validity findings.
- Filter saved Runs, reversibly archive review clutter, and compare up to four
  normalized portfolio curves with their exact parameters and costs.
- Build deterministic promotion evidence from expanding walk-forward folds,
  adjacent parameters, doubled costs, and aligned BTC/ETH holdouts.
- Run Buy & Hold and a formal Donchian ATR trend strategy.
- Publish a deterministic daily market-sentiment snapshot from seven market
  factors and source-linked news classifications.
- Display the sentiment result, factor detail, daily brief, and citations on
  the bilingual workspace homepage.

The research loop is implemented with Markdown reports and a product workspace.
Feature lineage, walk-forward validation, and broader derivatives datasets remain.

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

Create the locked Python environment and validate the repository:

```bash
uv sync --all-groups
bash scripts/validate_structure.sh
uv run ruff check .
uv run pytest --cov
```

Download a closed historical Kline range:

```bash
uv run quantos data download \
  --symbol BTCUSDT \
  --interval 1h \
  --start 2024-01-01T00:00:00Z \
  --end 2024-01-08T00:00:00Z
```

See [`docs/market-data`](docs/market-data/README.md) for validation and DuckDB
query commands. Run a backtest against the printed immutable dataset path:

```bash
uv run quantos backtest run \
  --dataset "<dataset-version-path>" \
  --strategy ema-cross \
  --fast 20 \
  --slow 50
```

See [`docs/backtest`](docs/backtest/README.md) for execution assumptions and
artifact details. The canonical Go/Python research service can run in its
production container with immutable data mounted from the workspace:

```bash
docker compose --profile research up --build research-api
```

The container never downloads data implicitly and exposes `/readyz` so a host
can wait for the configured Bundle before sending research traffic. See
[`apps/api`](apps/api/README.md) for deployment configuration.

Run a chronological parameter study:

```bash
uv run quantos experiment sweep \
  --dataset "<dataset-version-path>" \
  --fast 10,20 \
  --slow 40,50 \
  --min-bars 100
```

See [`docs/research`](docs/research/README.md) for study, comparison, and review
commands.

Build a validated sample of the daily intelligence contract:

```bash
uv run quantos intelligence build \
  --input examples/intelligence/sample-input.v1.json \
  --output-root var/quantos/intelligence
```

The example is labeled as sample data. A scheduled Agent or OpenClaw collector
can later publish current inputs through the same contract without controlling
the deterministic index methodology. See [`services/agent`](services/agent/README.md).

The first predeclared strategy study and its reproducible result artifact are
available in
[`docs/research/donchian-atr-study.md`](docs/research/donchian-atr-study.md).

Start the read-only research workspace:

```bash
cd apps/web
npm ci
npm run dev
```

The dashboard separates Overview, Strategies, Runs, and Data views. It presents
daily market intelligence, the committed BTC/ETH strategy study, cost stress,
research findings, and immutable evidence identities. See
[`docs/frontend`](docs/frontend/README.md).

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
