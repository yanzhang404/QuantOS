# QuantOS Web

The first product workspace presents reproducible strategy evidence from the
committed Donchian ATR study. It is intentionally read-only: no live trading,
credentials, or order actions are exposed.

The workspace supports English and Simplified Chinese. Use the language control
in the top-right corner to switch all research labels and conclusions without
changing the selected asset, observation window, or underlying evidence.

The strategy workbench adds synchronized Klines, executed buy/sell fills,
portfolio equity, underwater drawdown, and fill-level inspection for Buy &
Hold, EMA Cross, and Donchian ATR. Its compact visualization artifact preserves
the immutable dataset version and experiment Run ID behind each view.

The Backtest Lab connects to the local Go API and supports:

- editing strategy-specific parameters and simulation assumptions;
- submitting an idempotent historical backtest;
- polling queued and running Tasks to a terminal state;
- browsing persisted Task history and resulting Run IDs;
- loading a completed Run into the metric cards, Kline fills, equity, and
  drawdown charts;
- filtering immutable Run summaries and reversibly archiving review clutter;
- selecting two to four Runs for normalized return, parameter, cost, and metric
  comparison;
- reading the latest four-gate robustness review with explicit PASS/FAIL
  reasons and no automatic promotion.

The workspace uses a result-first layout: global workflows are in the top
navigation, reusable strategies are grouped in a folder-style library, and
capital/return/risk outcomes precede parameters and chart details. Parameter
inputs are generated from the versioned strategy catalog.

Copy `.env.example` to `.env.local` only when the API uses a non-default URL.
The default is `http://localhost:8080`.

## Local development

```bash
npm ci
npm run dev
```

Run the Go API from the repository root before submitting a manual backtest.

## Validation

```bash
npm run lint
npm test
```

The current dashboard imports the structured research artifact from
`examples/backtest/donchian-atr-study/results.json`. A versioned read-only API
will replace this build-time boundary when experiment browsing expands beyond
the first study.
