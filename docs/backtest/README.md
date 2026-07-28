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
- `fills.csv`;
- `equity.csv`;
- `report.md`.

Run identity also includes the actual evaluation start, end, and bar count, so
train, validation, and test slices cannot collide. Running the same dataset
slice, strategy, parameters, engine, and cost assumptions reuses the same run
ID.
