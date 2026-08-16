# US market radar replay

Run the deterministic opening-minute replay from the repository root:

```bash
quantos-us-radar replay --input examples/us-market-radar/bars.jsonl \
  --min-score 0 --push-interval 300 \
  --output-jsonl data/us-market-radar/demo-reports.jsonl
```

Evaluate saved alerts against later underlying bars:

```bash
quantos-us-radar evaluate \
  --reports examples/us-market-radar/alerts.jsonl \
  --bars examples/us-market-radar/outcome-bars.jsonl \
  --horizons 5,15,30 --output data/us-market-radar/evaluation.json
```

The evaluator reports raw and direction-adjusted forward return plus maximum
favorable and adverse underlying excursion. It does not estimate option P&L.

The sample includes rising AAPL, falling NVDA, and comparatively flat SPY bars.
It demonstrates direction-neutral heat ranking; it is synthetic test data and
not a historical trading claim.

Add the normalized option-chain fixture to exercise the complete two-stage
funnel. The scorer aligns calls with rising momentum and puts with falling
momentum, but labels the result as research rather than an order recommendation:

```bash
quantos-us-radar replay --input examples/us-market-radar/bars.jsonl \
  --option-chain examples/us-market-radar/option-chain.json \
  --min-score 35 --output-jsonl data/us-market-radar/options-demo.jsonl
```
