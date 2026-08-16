# ADR-0005: Screen US equities before subscribing to options

- Status: Accepted
- Date: 2026-08-16

## Context

QuantOS needs to surface liquid, fast-moving US underlyings during the regular
session so a human can investigate intraday option opportunities. Streaming the
entire listed-options quote universe is unnecessarily expensive and noisy. Heat
also measures attention, not whether an option contract is executable at a
reasonable spread.

## Decision

Build the workflow in two stages. This change implements stage one:

1. stream exchange-wide one-minute US equity bars through a provider contract;
2. maintain bounded in-memory rolling windows by symbol;
3. rank underlying heat using absolute momentum, short-horizon volume ratio,
   dollar volume, range expansion, VWAP displacement, and momentum acceleration;
4. publish the top ranked underlyings through configurable notifiers with a
   minimum score and cadence;
5. persist versioned JSON reports for replay and outcome review.

Stage two will subscribe only to option chains for the highest-ranked
underlyings. It will calculate a separate option tradability score from NBBO
spread, quote freshness, volume, open interest, IV, Greeks, and days to expiry.
Heat, direction, option tradability, and risk flags must remain separate fields.

The first live provider is Alpaca minute-bar WebSocket data. `sip`, `iex`, and
`delayed_sip` feeds are explicit configuration. Credentials are read only from
`APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`. Recorded JSON Lines bars provide a
deterministic replay path without credentials.

The worker observes and notifies only. It cannot access accounts, size
positions, choose orders, or place trades.

## Invariants

- All timestamps are timezone-aware and stored in UTC.
- Only regular-session bars from 09:30 through 16:00 America/New_York contribute
  to rankings unless a future schema explicitly identifies another session.
- Updated bars replace the same symbol/timestamp rather than double-counting.
- A report identifies its schema version, provider, generation time, and input
  bar count.
- Notifications are rate-limited summaries; every update is still eligible for
  local report persistence.
- A missing or rejected live-data entitlement fails loudly rather than silently
  falling back to a different feed.

## Consequences

Positive:

- full-market equity traffic is manageable with minute bars;
- expensive option subscriptions are reserved for a small candidate set;
- replay tests and captured reports make scoring changes reviewable;
- live execution remains outside the research boundary.

Tradeoffs:

- one-minute bars cannot detect sub-minute microstructure;
- short-window volume ratio is not yet the same-time-of-day historical RVOL
  baseline planned for a later dataset-backed version;
- the stage-one liquidity score is an underlying proxy and must not be presented
  as option-contract tradability.
