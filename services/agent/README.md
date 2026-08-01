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

Candidate proposals use the bounded `candidate-proposal.v1` contract. Source
code, commands, credentials, and trading instructions are not accepted fields.
The durable lifecycle separates proposal, implementation evidence, a passed
robustness artifact, and an explicit human decision. See
[ADR-0018](../../docs/adr/0018-guarded-candidate-lifecycle.md).

## Candidate lifecycle

Start from a contract-shaped proposal:

```bash
uv run quantos candidate propose \
  --input examples/candidates/sample-proposal.v1.json \
  --output-root var/quantos/candidates
```

The returned 16-character proposal ID is used for later transitions. Attach a
repository-owned Python symbol and deterministic test identifiers only after
the implementation exists:

```bash
uv run quantos candidate implemented \
  --id <proposal-id> \
  --implementation quantos_strategy.example.ExampleStrategy \
  --test-id tests.strategy.test_example_signals \
  --actor implementation-agent
```

`candidate attach-review` accepts a real `robustness.json` only when it is
complete, names the same strategy slug, and passes the exact walk-forward,
neighboring-parameter, doubled-cost, and multiple-market gates. Finally,
`candidate decide --decision approve|reject` records a human actor and a
20–500-character rationale. Approval changes research state only; it never
registers code, places orders, or enables live trading.

`quantos candidate list` reads the atomic records. The Go API and workspace use
the same versioned read model but expose no lifecycle mutation endpoint.

To spend one of the current UTC ISO week's one or two review slots:

```bash
uv run quantos candidate prepare-draft \
  --id <proposal-id> \
  --candidate-root var/quantos/candidates \
  --draft-root var/quantos/candidate-drafts \
  --weekly-limit 2
```

Only `proposed` candidates with no more than six parameters and three intervals
qualify. The same proposal cannot be scheduled twice, and a weekly limit cannot
be loosened after the first package. The atomic directory contains
`proposal.json`, `review-checklist.json`, and `PULL_REQUEST.md`; no branch or
remote PR is created. `quantos candidate list-drafts` shows the prepared queue.
See [ADR-0019](../../docs/adr/0019-rate-limited-candidate-draft-scheduling.md).

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
