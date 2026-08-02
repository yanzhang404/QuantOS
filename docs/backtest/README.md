# Backtest

The V0.1 engine replays one immutable Kline dataset through explicit Market,
Signal, Risk, Order, Fill, Portfolio, and Metric events.

## Execution semantics

- Strategies see a Kline only after it closes.
- A close-generated signal is risk-checked immediately.
- An approved target executes at the next Kline open.
- Buys pay positive fixed slippage; sells pay negative fixed slippage.
- Fees are proportional to executed notional.
- The portfolio is long-only and cannot spend more cash than it owns.
- The final position is liquidated by default and the assumption is reported.

See [ADR-0004](../adr/0004-next-bar-open-execution.md).

Aligned external features are also controlled by the event clock. Strategies
receive only the immutable observation attached to the current closed-bar
`MarketEvent`; they cannot load feature files directly.

## Run

```bash
uv run quantos backtest run \
  --dataset "<immutable-dataset-version>" \
  --strategy ema-cross \
  --fast 20 \
  --slow 50 \
  --initial-cash 100000 \
  --fee-bps 10 \
  --slippage-bps 5
```

The command writes a content-addressed experiment directory containing:

- `run.json` with dataset, strategy, engine, parameter, and metric versions;
- `metrics.json`;
- `bars.csv` with at most the latest 2,000 evaluated OHLCV bars for visualization;
- `fills.csv`;
- `equity.csv`;
- `report.md`.

Run identity also includes the actual evaluation start, end, and bar count, so
train, validation, and test slices cannot collide. Running the same dataset
slice, strategy, parameters, engine, and cost assumptions reuses the same run
ID.

Run the initial funding-filtered EMA research strategy with an exact causal
feature-dataset version:

```bash
uv run quantos backtest run \
  --dataset "<immutable-spot-dataset-version>" \
  --strategy funding-filtered-ema \
  --fast 20 \
  --slow 50 \
  --max-funding-rate 0.0001 \
  --feature-dataset "<aligned-funding-feature-version>" \
  --start 2024-01-01T00:00:00Z \
  --end 2025-01-01T00:00:00Z
```

The aligned feature manifest must bind the same Spot dataset version and cover
every selected Kline. Missing or stale funding forces zero exposure. Supplying
an external feature dataset to a strategy that does not consume it is rejected.
New `experiment-artifacts.v4` Runs include the full consumed feature manifest in
their identity, `run.json`, and report. See
[ADR-0025](../adr/0025-feed-versioned-features-through-market-events.md).

`funding-filtered-ema` remains a research hypothesis. A successful execution is
not promotion evidence; chronological holdout, neighboring threshold, cost, and
market sensitivity checks are still required.
