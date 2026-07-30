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
- loads a successful Experiment into every synchronized result view;
- preserves the read-only safety boundary around live execution.

Completed manual runs now replace the build-time strategy result when their
immutable dataset identity matches the selected workspace view. The selected
Run drives aggregate metrics, Kline fill markers, the fill table, portfolio
equity, position, and drawdown. Changing the strategy, asset, or observation
window returns the workspace to its committed baseline until another compatible
history record is selected.

Multi-Run comparison and Experiment filtering are the next frontend boundary.
