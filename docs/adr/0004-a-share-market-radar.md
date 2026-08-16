# ADR-0004: Add a read-only A-share Market Radar to market-data

- Status: Accepted
- Date: 2026-08-16

## Context

QuantOS V0.1 was initially scoped to historical crypto research. The product now
also needs a small A-share market-observation loop: acquire a full-market quote
snapshot, identify unusual stocks, and rank themes by heat and its rate of
change. This is market-data research, not a strategy, backtest, or execution
capability.

## Decision

Implement Market Radar as Python code inside `services/market-data`, using the
existing modular-monolith and Go/Python boundaries.

- A provider normalizes vendor responses into an exchange-neutral `StockQuote`.
- The first live provider uses Eastmoney's read-only public quote endpoint and
  has no credentials or trading operations.
- Theme membership is an explicit, versionable JSON input. Vendor classification
  models do not leak into the scoring domain.
- The worker CLI is a composition root and supports deterministic JSON replay.
- Radar output uses the versioned `market-radar/v0.1` report contract.
- State stores only recent theme scores required to calculate velocity and
  acceleration; it is disposable, local analytical state.

An individual stock is unusual when it has at least two configured triggers, or
its absolute price move exceeds the extreme-move threshold. Theme heat is a
bounded 0-100 weighted score made from mean return, advancing breadth, unusual
stock ratio, and turnover intensity. Velocity is score change per hour.
Acceleration is velocity change per hour squared and therefore needs three
chronologically distinct snapshots.

## Consequences

Positive:

- all vendor-specific behavior remains behind a tested provider boundary;
- recorded snapshots make detection and ranking reproducible;
- no live-trading authority or credentials are introduced;
- additional A-share providers can implement the same protocol.

Tradeoffs:

- the first public endpoint has no formal vendor SLA and may require adapter
  maintenance;
- theme quality depends on the supplied mapping and its versioning;
- point-in-time snapshots do not replace historical, survivorship-safe research
  datasets.
