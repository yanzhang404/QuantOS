# EMA Cross Backtest Example

First create or select one immutable market dataset, then run:

```bash
uv run quantos backtest run \
  --dataset "data/market/spot/exchange=binance/symbol=BTCUSDT/interval=1h/version=<id>" \
  --strategy ema-cross \
  --fast 20 \
  --slow 50 \
  --initial-cash 100000 \
  --fee-bps 10 \
  --slippage-bps 5
```

The JSON response contains the deterministic run ID, metrics, and artifact path.
Review `report.md` together with `fills.csv` and `equity.csv`; a positive result
is a historical simulation, not evidence of future profitability.
