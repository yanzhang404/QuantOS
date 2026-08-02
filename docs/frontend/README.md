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

Current snapshots are produced by the separate allow-listed collector and
deterministic publisher commands. Until the local empirical history reaches 30
daily observations, the API and page preserve the `partial` status instead of
presenting neutral calibration as mature evidence. Scheduling and last-success
health are the next delivery boundary.

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
- binds the immutable bundle, dataset version, content hash, symbol, interval,
  and evaluation range automatically;
- polls queued/running Tasks until success or failure;
- displays persisted Task history and resulting Run IDs;
- loads a successful Experiment into every synchronized result view;
- preserves the read-only safety boundary around live execution.

Completed manual runs replace the build-time strategy result when their exact
immutable dataset identity matches the selected workspace member. Each new Run
serves a bounded Kline tail from its own `bars.csv`, so the selected Run drives
aggregate metrics, Kline fill markers, the fill table, portfolio equity,
position, and drawdown across supported timeframes. Changing the strategy,
asset, interval, or observation window returns the workspace to its committed
baseline until another compatible history record is selected.

The Runs view uses the API Run catalog for exact strategy, symbol, timeframe,
and archive filtering. A researcher may select two to four Runs for normalized
equity comparison, inspect metric/input differences, and reversibly archive a
Run without changing its immutable experiment artifacts.

The same view reads the latest validated robustness review and shows four
explicit promotion gates. Green/red status always includes PASS/FAIL text and a
reason. Passing supports a later human promotion decision and never changes a
strategy lifecycle state automatically.

The Overview candidate card reads `GET /api/v1/candidates`. It replaces the
previous hard-coded candidate count with validated lifecycle records and shows
proposal, implementation, review-ready, approval, and rejection totals. The
browser has no candidate mutation endpoints or decision controls; human
decisions remain deliberate CLI operations until authenticated identities are
available.

The same card reads `GET /api/v1/candidate-drafts` and displays the occupied
slots for the latest scheduled ISO week. It exposes package metadata only; the
generated proposal, checklist, and pull-request body remain server-side review
artifacts.

## Strategy manifests and intervals

The versioned strategy catalog supplies category, lifecycle stage,
implementation reference, supported intervals, and parameter specifications.
The Backtest Lab generates its inputs from that manifest, so EMA, Donchian, and
benchmark strategies expose different editable parameters without duplicating
form definitions.

The product recognizes `5m`, `15m`, `1h`, `4h`, and `1d`. The Data and Overview
views import a compact projection of verified bundle `47a8b29be444e2ba`, which
contains BTCUSDT and ETHUSDT for all five intervals from 2021-01-01 through the
exclusive 2026-08-01 UTC boundary. The workspace exposes the latest boundary,
total row count, and preserved exchange-source gaps. The interval selector now
submits the matching immutable bundle member, while strategy manifests prevent
unsupported strategy/timeframe combinations. Committed comparison evidence
remains 4-hour data; newly submitted Runs provide their own exact Kline view.
