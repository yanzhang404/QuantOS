# ADR-0006: Enrich top US equity candidates with option snapshots

- Status: Accepted
- Date: 2026-08-16

## Context

ADR-0005 establishes equity-first screening and reserves full option-quote
streaming for a bounded candidate set. The product still needs evidence that a
hot underlying has at least one contract with a fresh two-sided market and
usable liquidity before notifying a human.

## Decision

At each configured equity notification interval, query read-only option-chain
snapshots and contract metadata for at most the top ten underlyings. Restrict the
query to expirations within seven calendar days and strikes within 20 percent of
the underlying price. This cadence is sufficient for initial screening; a later
change may subscribe the selected contracts to WebSocket NBBO updates if stored
outcome evidence justifies the extra bandwidth.

Normalize quote, trade, daily volume, open interest, IV, and Greeks into an
exchange-neutral option contract snapshot. Calculate a separate 0-100
tradability score from:

- bid/ask spread: 35 percent;
- quote freshness: 15 percent;
- daily volume: 15 percent;
- open interest: 15 percent;
- delta range: 10 percent;
- option mid-price range: 10 percent.

Missing or inadequate volume/open interest, a one-sided market, excessive
spread, or stale quote makes a contract ineligible regardless of score. Zero
DTE, indicative data, and extreme IV remain visible risk flags. For concise
momentum monitoring, rising underlyings show calls and falling underlyings show
puts; this is a labeling convention, not a claim that the contract should be
bought.

Alpaca `opra` and `indicative` feeds are explicit settings. The implementation
never silently downgrades feed quality. JSON option-chain replay is the
deterministic acceptance path.

## Consequences

Positive:

- alerts now distinguish attention from executable liquidity;
- request volume is bounded by the equity shortlist;
- wide-spread and unverifiable contracts cannot appear eligible;
- saved reports contain the exact evidence shown to the user.

Tradeoffs:

- five-minute snapshot refreshes may miss sub-minute quote deterioration;
- open interest is daily rather than intraday;
- momentum-aligned call/put filtering does not model reversal strategies;
- a production webhook and entitled market-data account are still required for
  unattended live delivery.
