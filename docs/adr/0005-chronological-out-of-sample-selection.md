# ADR-0005: Select parameters chronologically before holdout evaluation

- Status: Accepted
- Date: 2026-07-27

## Context

Selecting parameters using the same observations later reported as test
performance leaks information from evaluation into model choice. Random
train/test splits also destroy time order and can allow future market regimes to
influence earlier decisions. A reproducible research platform needs the
selection rule, exact ranges, and robustness assumptions to be inspectable.

## Decision

QuantOS parameter studies use contiguous, non-overlapping train, validation,
and test segments in market-time order.

Every valid parameter candidate runs on train and validation. Candidates are
ranked only by validation Sharpe ratio with deterministic parameter ordering as
the tie-breaker. Only the selected winner runs on the untouched test segment.
That same winner also runs on the test segment with doubled fees and slippage.

Each underlying backtest Run ID includes the actual evaluation start, end, and
bar count in addition to the immutable parent dataset identity. The study links
all candidate, holdout, and stress Run IDs and records its split ranges,
selection policy, leaderboard, and automated review findings.

## Consequences

Positive:

- future observations cannot influence earlier candidate evaluation;
- reported holdout results are not used to select parameters;
- range-aware identities prevent train, validation, and test artifact collisions;
- cost stress and deterministic review findings make common fragility visible.

Tradeoffs:

- one chronological split has higher variance than walk-forward analysis;
- cold-starting each segment can reduce usable observations for slow features;
- validation Sharpe is only one selection criterion and can be unstable;
- automated findings do not replace human research review.

Walk-forward evaluation, purged cross-validation, funding data, feature lineage,
and richer sensitivity analysis remain future work.
