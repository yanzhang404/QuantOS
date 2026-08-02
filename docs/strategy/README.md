# Strategy

Strategies receive market and fill events and emit target exposure. They cannot
call exchanges, place orders, or maintain authoritative account state.

## Built-in strategies

### Buy and hold

The benchmark observes the first closed bar, requests the configured maximum
exposure, fills at the next open, and holds until the engine's configured final
liquidation. It provides a passive baseline under the same fee and slippage
assumptions as active strategies.

### EMA cross

The example trend strategy is long while the fast EMA is above the slow EMA and
flat otherwise.

### Donchian ATR

The first formal research strategy:

- enters when the current close is strictly above the highest high of the
  preceding `entry_period` bars;
- exits when the current close is strictly below the lowest low of the
  preceding `exit_period` bars;
- sizes exposure from ATR as
  `target annual volatility / annualized ATR percentage`;
- caps exposure at `max_exposure`;
- only rebalances when target exposure moves by `rebalance_threshold`.

The channel excludes the current bar. ATR may include the current closed bar
because the resulting signal cannot fill until the next bar opens. The strategy
is long-only and makes no claim of profitability.

```bash
uv run quantos backtest run \
  --dataset "<immutable-dataset-version>" \
  --strategy donchian-atr \
  --entry-period 55 \
  --exit-period 20 \
  --atr-period 20 \
  --target-annual-volatility 0.20 \
  --rebalance-threshold 0.05 \
  --fee-bps 10 \
  --slippage-bps 5
```

## Feature identity

EMA, prior-high/low Donchian channels, and ATR are registered independently of
the strategy catalog. A new Run records the exact feature instances resolved
from its strategy parameters, including whether the current closed bar is used.
Inspect the contract with `uv run quantos backtest features`.
