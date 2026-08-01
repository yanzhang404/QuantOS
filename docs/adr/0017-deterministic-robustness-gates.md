# ADR-0017: Treat robustness checks as deterministic promotion gates

- Status: Accepted
- Date: 2026-08-01

## Context

A single chronological holdout and doubled-cost run are useful evidence but do
not show whether a selected parameter pair survives changing time windows,
nearby parameter choices, or another market. Candidate strategies need a
repeatable gate before an Agent or human can propose promotion.

## Decision

Add a versioned, content-addressed robustness review owned by the Python
research service. The first implementation evaluates EMA candidates with the
same backtest engine, immutable datasets, fees, slippage, and next-bar execution
contract used by ordinary Runs.

The review contains four deterministic gates:

1. **Walk-forward** divides observations into `fold_count + 2` contiguous
   blocks. Each fold expands the training prefix, ranks the configured grid on
   the immediately following validation block, and evaluates the winner on the
   next block. At least 60% of test folds and the median fold return must be
   positive.
2. **Neighboring parameters** evaluates the one-grid-step neighbors of the
   original winner on the original holdout. At least two valid neighbors are
   required; their median return must be positive and retain at least 50% of a
   positive winner return.
3. **Doubled costs** uses the existing holdout stress Run. It must remain
   positive and retain at least 50% of the positive base holdout return.
4. **Multiple markets** applies the fixed winner parameters to the aligned
   holdout window of at least one peer dataset with the same interval. The
   primary and every peer market must have positive return.

Thresholds and fold counts are stored in the review configuration. Every gate
records its inputs, linked Run IDs, observed values, and reason. The overall
review passes only when every gate passes. Passing is necessary evidence for a
promotion proposal, never an automatic promotion or trading authorization.

The first artifact set is `robustness.json`, `walk-forward.csv`, and
`review.md`. Dataset manifests and Run artifacts remain immutable and external
to the review directory.

## Consequences

Positive:

- promotion discussions receive consistent evidence instead of visual guesses;
- every stress result is reproducible through ordinary Run IDs;
- time, parameter, cost, and market fragility are separated visibly;
- future strategy-specific neighbor generators can reuse the gate contract.

Tradeoffs:

- the first runner supports EMA parameter grids only;
- post-selection neighbor analysis consumes the original holdout for
  robustness review, so it cannot be used to retune the winner;
- strict all-market positivity may reject useful diversifying strategies;
- more folds and candidates increase deterministic compute cost.
