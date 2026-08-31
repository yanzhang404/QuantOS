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

## Strategy visualization artifact

The web strategy workbench consumes a compact artifact derived from immutable
Kline versions and their matching experiment directories:

```bash
.venv/bin/python scripts/export_web_strategy_artifact.py \
  --study examples/backtest/donchian-atr-study/results.json \
  --market-root "<market-data-root>/market/spot" \
  --experiments-root "<experiment-root>" \
  --output examples/backtest/donchian-atr-study/visualization.json
```

The exporter preserves dataset hashes and Run IDs while bounding the browser
payload to the latest 240 bars for each asset and observation window.
