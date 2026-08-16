# ADR-0007: Evaluate radar alerts before optimizing scores

- Status: Accepted
- Date: 2026-08-16

## Context

A live alert and a plausible score do not establish predictive value. Adjusting
heat or tradability thresholds without stored forward outcomes would encourage
anecdotal tuning and overfitting.

## Decision

Persist every published alert and evaluate the underlying at explicit 5, 15,
and 30-minute horizons. For each symbol/horizon record:

- raw underlying return;
- direction-adjusted underlying return;
- maximum favorable underlying excursion;
- maximum adverse underlying excursion;
- whether an exact horizon bar was available.

Aggregate only complete outcomes into count, positive count, hit rate, mean
directional return, and mean excursions. Duplicate reports for the same symbol
and timestamp are evaluated once. Incomplete outcomes remain visible and are
not filled from later bars.

This evaluator measures the underlying signal only. It must not present these
returns as option P&L because option outcomes also require historical NBBO, IV,
Greeks, contract multiplier, fees, and execution assumptions.

## Consequences

Positive:

- score changes can be reviewed against saved evidence;
- missing bars cannot silently bias results;
- direction and raw movement remain independently inspectable;
- future option-level evaluation has an explicit baseline.

Tradeoffs:

- early samples have low statistical power;
- bar-level excursion is coarser than tick-level execution;
- results do not yet control for spread, slippage, regime, or repeated correlated
  alerts.
