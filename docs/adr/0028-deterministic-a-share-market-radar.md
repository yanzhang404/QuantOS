# ADR-0028: Monitor A-share heat with deterministic snapshots

- Status: Accepted
- Date: 2026-08-12

## Context

QuantOS needs to answer a narrower intraday question than the daily sentiment
brief: which A-share themes are attracting attention now, which stocks lead
them, and which themes are heating up relative to 30 and 60 minutes ago.
Ranking only the largest price moves detects events after they are already
obvious. Letting an Agent invent a heat score would make the ranking impossible
to reproduce. Public market responses are also untrusted and may be incomplete.

## Decision

Add a versioned `market-radar.v1` boundary owned by `services/agent`:

- a normalized CN-market input contains positive movers, observed prices and
  changes, industry/theme labels, anomaly reasons, source links, and optional
  relative-volume, turnover, 30-minute momentum, 20-day-high, and catalyst
  observations;
- the first collector calls only Eastmoney's fixed public A-share snapshot
  HTTPS endpoint with a bounded request, fixed market universe and sort,
  fixed timeout, no redirects, no credentials, and no caller-supplied URL;
- optional quantitative fields are never fabricated. Missing fields lower the
  stock's visible `data_coverage`, and collector output remains `partial`;
- `quantos-market-radar-v1.0.0` calculates `stock_heat_score` from price move,
  relative volume, turnover, 30-minute momentum, and a 20-day-high flag. It
  re-normalizes only across observed components and records every component;
- theme heat combines the mean of its three leading stock scores (70%) and
  observed mover breadth, capped at five stocks (30%);
- 30- and 60-minute acceleration subtract the matching score from the nearest
  immutable snapshot within a 15-minute tolerance. A missing baseline remains
  `null`;
- every refresh pins one normalized input per ten-minute UTC bucket, publishes
  an immutable timestamped snapshot plus an atomic `latest.json`, and records
  bounded refresh health. A failed collection or publication preserves the
  prior latest snapshot;
- a published timestamp bucket is write-once: an identical retry is
  idempotent, while different content for the same bucket is rejected. The
  `latest.json` pointer may only move forward, so replaying an older research
  input cannot silently make the current API regress;
- a nominally successful provider response with no valid movers is a collection
  failure, not evidence that market heat is empty;
- the deployment timer runs every ten minutes only inside the two weekday
  A-share sessions and does not catch up missed intraday runs;
- Go validates and serves only the trusted latest snapshot and refresh health.
  The web overview uses a clearly labelled sample when no live snapshot exists.

The radar is read-only research context. It cannot place orders, change risk
policy, promote a strategy, or trigger live or paper trading.

## Consequences

Positive:

- heat and acceleration rankings are deterministic, versioned, and testable;
- missing RVOL or turnover is visible instead of silently estimated;
- repeated refreshes can identify newly accelerating themes without mutable
  intraday state;
- collector outages do not replace the last valid view.

Tradeoffs:

- the public snapshot is not an exchange tape, so theme breadth means observed
  top movers rather than all industry or concept constituents;
- the first provider supplies price change, volume ratio, turnover, and one
  industry label, but not 30-minute return, 20-day-high state, or full concept
  membership;
- ten-minute polling can miss moves between snapshots and is not an HFT feed;
- the first scheduler does not carry an exchange-holiday calendar, so operators
  should disable it on exceptional non-trading weekdays until that calendar is
  added;
- catalyst text is source-linked context, not a causal or investment claim.
