# ADR-0024: Materialize derivatives features at the closed-bar decision time

- Status: Accepted
- Date: 2026-08-02

## Context

Funding and open-interest datasets have timestamps and frequencies that differ
from Spot Klines. A direct row join, nearest-neighbor match, or unrestricted
forward fill could select an observation that was unavailable when a strategy
made its decision or conceal stale and missing inputs.

QuantOS strategies observe a Kline only after it closes and submit targets for
the next bar open. Derivatives context therefore needs an explicit,
reproducible decision-time alignment before any strategy may consume it.

## Decision

Add an `aligned-derivatives.v1` feature-dataset family. One materialization binds
exactly one verified Spot Kline dataset version and one verified funding-rate or
open-interest dataset version. It selects an explicit Spot evaluation range and
an explicit positive maximum observation age.

For every selected Spot bar, the `asof-closed-bar.v1` policy:

1. sets the decision time to the Kline close time;
2. considers only derivatives observations whose timestamp is less than or
   equal to that decision time;
3. selects the most recent eligible observation;
4. emits feature values only when its age does not exceed the declared maximum;
5. otherwise emits a visible `no-prior-observation` or `stale-observation`
   reason, preserving the latest prior timestamp and age when one exists.

There is no interpolation, backward fill, future-nearest match, or implicit
default value. The output contains one row per selected Spot bar and records
the bar times, selected observation time, age, availability state, and typed
funding or open-interest values.

The immutable manifest records both input versions and content hashes, the
alignment-policy version, requested range, maximum age, matched/stale/missing
counts, schema and file hashes, and producer version. Output identity includes
the complete normalized rows and these consequential inputs. Verification
reloads Parquet, recomputes content identity, and proves that no selected
observation is later than its decision bar.

## Consequences

Positive:

- strategies can consume derivatives context without hidden lookahead;
- missing and stale source coverage remains measurable;
- every future Run can bind an exact aligned feature dataset;
- changing an input dataset, evaluation range, or age policy changes identity.

Tradeoffs:

- materialized rows duplicate decision-time metadata for auditability;
- maximum age is a research assumption and must be sensitivity-tested;
- this decision enables feature inputs but does not claim that they improve a
  strategy or authorize trading.
