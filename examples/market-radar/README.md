# Market Radar replay example

From the repository root, after installing `services/market-data`, run:

```bash
quantos-market-radar --provider json \
  --input examples/market-radar/quotes.json \
  --state data/market-radar/example-state.json --pretty
```

The recorded quote snapshot embeds theme membership so the output is completely
deterministic. `themes.json` demonstrates the separate mapping accepted by the
live Eastmoney provider.
