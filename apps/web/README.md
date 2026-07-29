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

## Local development

```bash
npm ci
npm run dev
```

## Validation

```bash
npm run lint
npm test
```

The current dashboard imports the structured research artifact from
`examples/backtest/donchian-atr-study/results.json`. A versioned read-only API
will replace this build-time boundary when experiment browsing expands beyond
the first study.
