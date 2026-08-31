# ADR-0009: Persist local backtest tasks as atomic JSON records

- Status: Accepted
- Date: 2026-07-29

## Context

Backtest contract v1 distinguishes user Tasks from deterministic experiment
Runs. The product now needs a first runnable control plane, durable local task
history, idempotent submission, and a bridge to Python research compute.

PostgreSQL remains the intended transactional metadata store, but the project
is still single-maintainer, local-first, and has no database deployment or
migration tooling. Introducing a database before the task lifecycle and query
patterns are exercised would add operations without improving the initial
workflow.

## Decision

Implement the first Go control plane as one process with:

- one atomic JSON file per Task under a configurable state root;
- a process-local mutex and idempotency index rebuilt from Task files at startup;
- one bounded in-process queue and one background worker;
- a fixed, argument-array Python command adapter for historical backtests;
- trusted data, artifact, and state roots supplied by server configuration.

The API resolves immutable dataset paths from validated dataset identity. User
requests cannot provide paths, commands, environment variables, or output
locations. The Python worker verifies the resolved dataset before execution and
continues to own content-addressed experiment artifacts.

Accepted Tasks transition through `queued`, `running`, and one terminal state.
After a process restart, non-terminal records become failed with a retryable
`service_restarted` error. They are never replayed silently.

The same idempotency key and identical request returns the existing Task. Reuse
of a deterministic Run remains independent: a new Task may complete with
`reused=true`.

## Consequences

Positive:

- task history survives local process restarts without external infrastructure;
- atomic replace prevents partially written Task records;
- the Go/Python boundary is explicit and shell injection is excluded;
- restart behavior avoids untracked duplicate compute;
- the store interface can later receive a PostgreSQL implementation.

Tradeoffs:

- only one API process may own a state root;
- task queries scan a small local catalog rather than a database index;
- in-process queues do not support horizontal scaling;
- PostgreSQL migration is required before multi-user or multi-process use.
