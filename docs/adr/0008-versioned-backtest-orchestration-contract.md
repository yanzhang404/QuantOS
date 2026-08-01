# ADR-0008: Version backtest orchestration contracts independently

- Status: Accepted
- Date: 2026-07-29

## Context

The deterministic backtest engine accepts Python objects and writes
content-addressed experiment directories. The product workspace now needs to
submit parameterized runs, observe task progress, and browse saved experiments.
Passing command-line arguments or Python persistence models directly through an
API would couple the Go control plane, Python compute plane, and web client.

A user submission and a deterministic experiment are also different records.
Every submission needs its own task lifecycle, while identical immutable inputs
should reuse the same Run ID and artifacts.

## Decision

Define a language-neutral `backtest.v1` JSON contract under
`packages/api-schema`. Version `1.0` covers:

- a backtest submission with an idempotency key, immutable bundle and resolved
  dataset identity,
  bounded evaluation range, strategy identity and parameters, and explicit
  cost/risk assumptions;
- a task record with queued, running, succeeded, failed, or cancelled state;
- a completed experiment record with metrics and relative artifact names;
- a discoverable strategy catalog with editable parameter specifications.

Python validation models implement the same boundary for the compute plane.
The future Go API will implement the JSON schema independently and contract
tests will keep the two representations compatible.

The API verifies bundle membership, then resolves a dataset version and Run ID
server-side. Requests cannot
contain filesystem paths, commands, arbitrary strategy names, or execution
instructions. This contract schedules historical simulations only and has no
live-trading capability.

Each accepted submission creates a Task ID. A successful task points to one
deterministic Run ID and reports whether existing artifacts were reused.
Retries with the same idempotency key return the original task instead of
creating another record.

## Consequences

Positive:

- browser, API, and worker communicate through an explicit stable boundary;
- task history preserves every intentional submission without duplicating
  deterministic experiments;
- immutable dataset and cost assumptions remain mandatory;
- strategy parameter forms can be generated from the catalog;
- unsafe paths and execution controls stay outside the public contract.

Tradeoffs:

- schema and language implementations require compatibility tests;
- adding a strategy or parameter may require a contract-version change;
- task persistence and execution are separate increments after this contract;
- version `1.0` intentionally omits multi-asset portfolios and parameter sweeps.
