# Frontend

The first read-only research workspace is implemented in `apps/web`. It exposes
the actual Donchian ATR study as an interactive strategy comparison:

- BTC/ETH and development/evaluation switching;
- returns, Sharpe, drawdown, trades, fills, and fees;
- Buy & Hold, EMA, and Donchian ATR comparison;
- doubled-cost evaluation stress;
- research findings and immutable dataset/Run IDs.

The workspace imports the committed structured result artifact at build time.
It also imports a compact strategy-visualization artifact derived from the
immutable Kline datasets and experiment CSV files. The strategy workbench
synchronizes:

- Kline price action and buy/sell fills;
- per-strategy equity and drawdown;
- position exposure and fill-level details;
- strategy, asset, and observation-window selection.

The next frontend boundary is a versioned read-only API for browsing multiple
datasets, runs, and studies. Interactive reruns, live trading, and order actions
remain disabled.

## Backtest Lab

The workspace now consumes the versioned local Task API for manual historical
backtests. A researcher can edit the active strategy parameters, initial cash,
fees, slippage, exposure limit, and final-liquidation assumption. The client:

- generates a unique idempotency key for each intentional submission;
- binds the immutable dataset version and content hash automatically;
- polls queued/running Tasks until success or failure;
- displays persisted Task history and resulting Run IDs;
- preserves the read-only safety boundary around live execution.

Completed manual runs do not yet replace the build-time Kline visualization.
Experiment detail and comparison endpoints are the next boundary for loading a
new Run's fills, equity, drawdown, and report into the charts.
