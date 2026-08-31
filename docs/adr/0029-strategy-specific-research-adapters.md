# ADR-0029: Bind chronological research to strategy-specific adapters

- Status: Accepted
- Date: 2026-08-31

## Context

The chronological study and four-gate robustness runner currently assume every
strategy is an EMA cross with `fast_period` and `slow_period`. QuantOS already
has a separate Donchian ATR implementation whose entry, exit, ATR, volatility,
exposure, and rebalance parameters have different constraints. Reusing EMA
field names or neighbor rules would create invalid evidence while appearing to
pass through the common backtest system.

## Decision

Introduce a bounded strategy-research adapter contract in the Python research
service. An adapter owns only strategy-specific research behavior:

- the strategy slug and implementation version;
- the canonical candidate parameter sets and deterministic tie-break order;
- construction of one strategy instance from an exact parameter set;
- the minimum bars needed by that parameter set;
- one-grid-step neighboring parameter generation; and
- a human-readable label for reports.

The shared runner continues to own chronological splitting, validation-only
selection, untouched holdout evaluation, doubled-cost stress, expanding
walk-forward folds, aligned peer markets, Run publication, and gate thresholds.
Adapters cannot access an exchange, filesystem, account, credential, risk
policy, or lifecycle transition.

The first two adapters are:

1. `ema-cross`, with the existing valid `fast_period < slow_period` grid; and
2. `donchian-atr`, with entry, exit, and ATR period grids, the invariant
   `exit_period <= entry_period`, and fixed volatility-targeting, exposure, and
   rebalance assumptions recorded in every Run.

Each grid axis is limited to 32 unique values and a study to 256 valid
candidates. These limits keep Agent- or CLI-supplied research work bounded
before any simulations or artifacts are created.

New study and robustness artifacts use `research-study.v2` and
`robustness-review.v2`. Candidate, fold, neighbor, and market records store a
canonical `parameters` object instead of EMA-specific fields. Read-only API and
workspace consumers continue to accept existing EMA `robustness-review.v1`
artifacts while validating v2 winner parameters against the named built-in
strategy. Candidate lifecycle attachment accepts either version only when the
strategy slug matches and all four gates pass.

## Consequences

Positive:

- Donchian ATR receives strategy-correct chronological and robustness evidence;
- additional built-in strategies can reuse the common gates without pretending
  to have EMA parameters;
- exact parameter assumptions remain content-addressed in ordinary Runs and
  review artifacts;
- promotion authority and all trading prohibitions remain unchanged.

Tradeoffs:

- multi-dimensional Donchian grids can increase deterministic compute cost;
- fixed risk-sizing parameters are recorded but not independently swept in the
  first Donchian adapter;
- v1 compatibility remains in API consumers until existing EMA reviews are
  retired.
