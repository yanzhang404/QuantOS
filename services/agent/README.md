# Agent Service

Owns tool-gated AI workflows and evidence links. Agents do not receive authority
to activate live trading.

Strategy discovery follows an explicit lifecycle:

```text
hypothesis → candidate implementation → deterministic tests
           → robustness review → human promotion decision
```

An agent may propose strategy code and parameter manifests, run historical
experiments, and summarize evidence. It may not silently mark a candidate
validated, promote it to a production signal, or bypass the shared risk and
backtest boundaries.

## Daily market intelligence

The first implemented Agent boundary is a deterministic daily sentiment and
brief publisher. An Agent or OpenClaw automation prepares a bounded
`intelligence.v1` JSON input containing seven rolling-percentile market factors
and source-linked news classifications. QuantOS validates that input, calculates
the fixed score, and writes one immutable daily snapshot plus `latest.json`.

```bash
uv run quantos intelligence build \
  --input examples/intelligence/sample-input.v1.json \
  --output-root var/quantos/intelligence
```

The input must use public HTTPS source URLs and contains no credentials,
commands, article bodies, or trading actions. The sample is explicitly marked
as sample data and is not a current market claim.
