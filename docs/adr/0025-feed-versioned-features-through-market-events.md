# ADR-0025: Feed versioned feature observations through MarketEvent

- Status: Accepted
- Date: 2026-08-02

## Context

The backtest engine currently sends strategies only normalized OHLCV bars. An
aligned derivatives dataset can be attached to a Run as metadata, but doing so
without feeding its values to strategy code would falsely imply that the Run
used those inputs. Passing an unversioned dictionary or allowing strategies to
load Parquet directly would bypass engine time control and reproducibility.

The first bounded research hypothesis is that a normal EMA trend entry may be
filtered when the latest causally available funding rate exceeds a configurable
crowding threshold. This is a hypothesis to test, not a promoted strategy or a
profit claim.

## Decision

Extend `MarketEvent` with an immutable tuple of generic `FeatureObservation`
records. Each observation contains:

- a feature ID and immutable feature-dataset version;
- availability (`matched`, `no-prior-observation`, or `stale-observation`);
- source observation time and age when present;
- an immutable tuple of typed decimal name/value pairs.

The engine accepts already verified aligned feature datasets. Before replay it
requires one row per selected Kline, exact symbol and interval identity, exact
bar open and decision times, unique feature series, and the same Spot dataset
version/content hash as the Run. The engine constructs feature observations;
strategies cannot read dataset files or advance the feature clock.

Add a `funding-filtered-ema` research strategy with parameters:

- `fast_period` and `slow_period` for the ordinary closed-bar EMAs;
- `max_funding_rate` as the largest matched rate that permits long exposure.

It targets long exposure only when the fast EMA is above the slow EMA and the
matched funding rate is at or below the threshold. Missing or stale funding is
fail-closed to zero exposure. Approved signals still pass through the existing
long-only risk engine and execute at the next Kline open.

New experiment artifacts use `experiment-artifacts.v4`. Their content identity
and `run.json` bind every consumed feature dataset's version, content hash,
policy, source input versions, range, maximum age, and availability counts.
Ordinary strategies reject supplied external feature datasets so Runs cannot
claim unused inputs. Existing v2/v3 Runs remain readable.

## Consequences

Positive:

- feature values remain controlled by the deterministic event clock;
- a Run can prove both the feature definition and materialized input version;
- missing-data behavior is explicit and conservative;
- the first derivatives strategy has editable, strategy-specific parameters.

Tradeoffs:

- the event schema and artifact schema receive intentional version bumps;
- the initial strategy consumes funding only; OI strategy research follows
  after enough prospective history exists;
- usefulness still requires chronological holdout and sensitivity evidence.
