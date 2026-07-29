# QuantOS Web

The first product workspace presents reproducible strategy evidence from the
committed Donchian ATR study. It is intentionally read-only: no live trading,
credentials, or order actions are exposed.

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
