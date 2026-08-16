# Market Data Service

Owns exchange adapters, normalization, validation, Parquet publication, and
dataset version manifests. The V0.1 implementation belongs here.

## A-share Market Radar v0.1

The Python package in this directory adds a read-only market-observation loop:

- full-market A-share snapshots through a provider contract;
- an Eastmoney public-quote adapter and deterministic JSON replay provider;
- configurable stock anomaly detection;
- theme heat, heat velocity, and heat acceleration;
- a versioned JSON report and local history state.

Install and test from the repository root:

```bash
python -m pip install -e services/market-data
python -m unittest discover -s services/market-data/tests -v
```

Run from a recorded snapshot:

```bash
quantos-market-radar --provider json --input quotes.json --pretty
```

Run against the public provider with a versioned theme map:

```bash
quantos-market-radar --provider eastmoney --theme-map themes.json \
  --state data/market-radar/state.json --output artifacts/market-radar.json
```

The theme map accepts either `{"000001": ["银行"]}` or
`{"银行": ["000001"]}`. Without a map the report still contains stock
anomalies, but theme rankings are empty. Thresholds and score definitions are
documented in [ADR-0004](../../docs/adr/0004-a-share-market-radar.md).

External responses are untrusted: malformed and suspended quotes are skipped,
and an entirely invalid response fails the run instead of publishing an empty
snapshot.

## US equity heat radar

The US radar is stage one of an intraday-options screening funnel. It consumes
one-minute equity bars, filters the NYSE regular session using the
`America/New_York` timezone, and ranks underlyings by:

- absolute five-minute momentum;
- current volume versus the preceding five bars;
- five-minute dollar volume;
- range expansion and VWAP displacement;
- one-minute momentum acceleration.

Heat is direction-neutral: a fast downside move can rank above an upside move.
The report includes direction separately. `underlying_liquidity_score` is only
an equity proxy, so an equity-only report keeps
`option_tradability_status=not_evaluated`.

When `--options-feed opra` or `--options-feed indicative` is enabled, the second
stage queries option snapshots only for the hottest underlyings. It scores
two-sided spread, freshness, volume, open interest, delta, and mid-price range;
IV and zero-DTE conditions remain visible risk flags. Missing/low volume or open
interest, stale quotes, and wide spreads are hard eligibility failures.

Replay the included synthetic opening sequence:

```bash
quantos-us-radar replay --input examples/us-market-radar/bars.jsonl \
  --option-chain examples/us-market-radar/option-chain.json \
  --min-score 0 --output-jsonl data/us-market-radar/demo-reports.jsonl
```

For live use, set credentials in the environment and choose the entitled feed:

```bash
export APCA_API_KEY_ID="..."
export APCA_API_SECRET_KEY="..."
quantos-us-radar live --feed sip --options-feed opra --webhook-url "..." \
  --webhook-format slack --output-jsonl data/us-market-radar/reports.jsonl
```

Supported webhook bodies are Slack-compatible, WeCom text, and generic
`{"text": "..."}` JSON. Credentials and webhook URLs must never be committed.
The live stream reconnects after transport failures but fails immediately when
Alpaca rejects authentication, entitlement, or subscription configuration.

To keep it running continuously, copy `.env.example` to an ignored `.env`, fill
the values locally, and start the opt-in Compose profile:

```bash
docker compose --profile us-radar up --build -d us-market-radar
```

The process may remain connected outside regular hours, but extended-hours bars
do not enter the rankings. A new New York trading date resets the rolling state.
See [ADR-0005](../../docs/adr/0005-us-equity-live-radar.md) and
[ADR-0006](../../docs/adr/0006-top-candidate-option-snapshots.md).

### Outcome review

Saved equity or option-enriched reports can be evaluated against later minute
bars:

```bash
quantos-us-radar evaluate --reports data/us-market-radar/reports.jsonl \
  --bars captured-bars.jsonl --horizons 5,15,30 \
  --output data/us-market-radar/evaluation.json
```

The output records raw/direction-adjusted underlying return and maximum
favorable/adverse excursion. Exact horizon bars are required; incomplete
observations do not enter summary statistics. This is underlying-signal review,
not an option-P&L backtest. See
[ADR-0007](../../docs/adr/0007-radar-outcome-evaluation.md).
