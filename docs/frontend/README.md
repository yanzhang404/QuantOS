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

The application now exposes four hash-addressable product views:

- Overview for market intelligence, latest evidence, candidate status, and data health;
- Strategies for the folder-style library, result-first metrics, parameters, and charts;
- Runs for fixed experiment comparison, cost stress, and research findings;
- Data for immutable identities, interval coverage, and lineage.

The previous report-style hero and large lifecycle diagram have been removed.
On wide screens the Strategies view uses a strategy tree, central result area,
and sticky parameter panel; narrower layouts collapse without hiding the
underlying backtest controls.

The visual system uses a bright research-workbench theme: a warm off-white
canvas, white evidence cards, restrained green actions, and explicit red/amber/
green semantic states. Cards use compact 18px spacing and low-contrast shadows
instead of large dark containers. At intermediate widths the intelligence
summary moves its three supporting KPIs onto a second row, and the header hides
secondary status copy before navigation can overlap.

The intelligence heading uses its own vertical title container rather than
inheriting generic flex behavior. Supporting labels, metadata, parameter names,
table values, and chart descriptions use a 9–14px scale with increased line
height; 7–8px type is reserved for dense chart axes only.

## Daily market intelligence

The Overview view requests the latest validated sentiment snapshot from
`GET /api/v1/intelligence/latest` and presents the composite score first,
followed by its change, market/news components, seven factor scores, daily
brief, and source links. If no daily publication exists, the page uses a
committed fixture that is visibly labeled as non-current sample data.

The sentiment level uses a labeled red-to-amber-to-green scale: fear is red,
neutral is amber, and greed is green. The separate change value remains green
for an increase and red for a decrease. Factor and brief detail is collapsed by
default to keep the first viewport focused.

The UI never calculates the index itself. The deterministic methodology and
input provenance remain owned by the versioned Agent contract.

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

## Strategy manifests and intervals

The versioned strategy catalog supplies category, lifecycle stage,
implementation reference, supported intervals, and parameter specifications.
The Backtest Lab generates its inputs from that manifest, so EMA, Donchian, and
benchmark strategies expose different editable parameters without duplicating
form definitions.

The product recognizes `5m`, `15m`, `1h`, `4h`, and `1d`. The Data and Overview
views import a compact projection of verified bundle `27d21dafc1ae305e`, which
contains BTCUSDT and ETHUSDT for all five intervals over 2024 Q1. Strategy
visualization and committed comparison evidence remain 4-hour data until the
backtest task resolver is connected to these new immutable versions.
