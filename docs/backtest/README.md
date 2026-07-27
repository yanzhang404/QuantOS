# Backtest

The initial engine operates on Kline events with a deterministic clock. It must
model fees and fixed slippage, prevent look-ahead access, and emit trades,
portfolio state, metrics, and an equity curve.
