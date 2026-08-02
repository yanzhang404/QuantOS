# API Schema

Language-neutral request and response contracts between the web client, future
Go control plane, and Python research worker.

`schemas/backtest.v1.schema.json` is the normative JSON boundary for historical
backtest submission, task lifecycle, completed experiment records, and the
editable built-in strategy catalog. Python validation models live in
`quantos_api_contracts`.

The contract intentionally contains no filesystem paths, shell commands,
credentials, paper-trading controls, or live-execution controls.

Contract v1 preserves exact decimal inputs as JSON strings. Strategy periods
remain JSON integers. A submission with unknown fields or strategy parameters
is rejected instead of silently applying defaults.

`schemas/intelligence.v1.schema.json` defines the daily market-factor/news input
and the immutable sentiment snapshot consumed by the read-only homepage API.
The score remains deterministic; agent-authored text is stored only as
source-linked commentary.

`schemas/intelligence-refresh-health.v1.schema.json` defines the bounded
single-writer job status exposed beside the latest snapshot. Staleness is
derived by the Go API and is not persisted by the writer.

`schemas/candidate.v1.schema.json` defines the bounded Agent proposal input;
`schemas/candidate-record.v1.schema.json` defines its durable transition record.
They contain hypotheses, manifest-shaped parameters, research plans, public
HTTPS citations, evidence identities, and actor history—but no code, command,
path, credential, or trading-action fields. Python owns validated mutations and
Go exposes the same records read-only.

`schemas/candidate-draft.v1.schema.json` defines the rate-limited review package
prepared from an existing proposal. It records one of at most two weekly slots
and fixed artifact names; preparation itself performs no GitHub mutation.
