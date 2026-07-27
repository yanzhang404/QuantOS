# ADR-0001: Start with a modular monolith

- Status: Accepted
- Date: 2026-07-27

## Context

QuantOS spans market data, research, backtesting, experiments, risk, and future
execution. The domain is early, the initial team is small, and the boundaries
will change while the first reproducible research loop is built. Deploying each
area independently now would introduce network contracts, distributed tracing,
failure handling, and operational overhead before those costs solve a measured
problem.

## Decision

Build QuantOS as a modular monolith in one repository and coordinated deployment
model. Keep domain modules isolated through explicit APIs, schemas, and ownership
rules. Separate processes are allowed for the Go/Python runtime boundary, but
they are not independently governed microservices.

A module may become a service only after:

1. its domain contract is stable;
2. it has an independent scaling or reliability requirement;
3. operational ownership is clear; and
4. migration cost is lower than continued coupling cost.

## Consequences

Positive:

- local development, testing, and deployment remain simple;
- refactoring domain boundaries is inexpensive;
- cross-module behavior can be tested deterministically;
- a small team can operate the whole system.

Tradeoffs:

- modules share a release cadence;
- process-level isolation is limited;
- discipline is required to prevent internal coupling.

We mitigate coupling with package ownership, versioned contracts, and tests
across boundaries rather than premature network separation.
