# ADR-0002: Split platform and research responsibilities between Go and Python

- Status: Accepted
- Date: 2026-07-27

## Context

QuantOS needs reliable APIs, orchestration, risk controls, and future real-time
connectivity. It also needs a productive numerical ecosystem for data analysis,
features, strategies, backtesting, and AI tools. Forcing both workloads into one
language would sacrifice either platform ergonomics or research velocity.

## Decision

Use Go for the platform control plane and Python for the research compute plane.

Go owns:

- APIs and product-facing services;
- project and task orchestration;
- future risk enforcement, order management, and exchange adapters;
- operational state and health.

Python owns:

- historical data processing;
- factors and strategies;
- backtest execution and metrics;
- experiment tools and research-oriented AI tool execution.

Integration uses explicit, versioned schemas. Strategies produce signals or
portfolio intent and cannot invoke Go execution adapters directly. Persistence
tables and in-memory types are not cross-language contracts.

## Consequences

Positive:

- each workload uses its strongest ecosystem;
- execution authority stays outside research code;
- schema boundaries make ownership and testing explicit.

Tradeoffs:

- two toolchains and dependency graphs must be maintained;
- serialization and compatibility testing are required;
- local orchestration must manage multiple runtimes.

V0.1 should choose the simplest transport that supports deterministic local
workflows; this ADR does not require a distributed service architecture.
