# ADR-0022: Version strategy features and resolve them into every new Run

- Status: Accepted
- Date: 2026-08-02

## Context

Strategy manifests expose editable parameters, but completed Runs identify only
the strategy class and parameter values. EMA, prior-bar Donchian channels, and
ATR are currently embedded in strategy code, so a reviewer cannot inspect their
input columns, causality rule, warmup, or implementation version independently.

## Decision

Add a code-owned `feature-registry.v1` with bounded built-in definitions and
strategy bindings. Each definition records its semantic version, implementation
symbol, Kline inputs, current-bar policy, warmup parameter, and description.

Before publishing a new Run, resolve the selected strategy parameters into
concrete feature instances. Persist each instance in `run.json` with:

- feature and instance identifiers;
- semantic version and definition SHA-256;
- exact implementation symbol and input columns;
- resolved parameters and warmup bars;
- whether the current closed bar is included.

Resolved feature lineage participates in the content-addressed Run ID. Bump new
artifacts to `experiment-artifacts.v3`; existing v2 artifacts remain readable.
Buy and Hold intentionally resolves to no derived features. Unknown test-only
strategies also resolve to an empty list rather than claiming registered
lineage.

## Consequences

Positive:

- strategy parameter changes can be traced to exact feature instances;
- causality and prior-bar exclusions become inspectable rather than prose only;
- changing a feature definition creates a different Run identity;
- future feature materialization can reuse the same contract.

Tradeoffs:

- the first registry covers only features already used by built-in strategies;
- indicator values remain computed inside the event-driven strategies for now;
- feature-version changes require intentional artifact and evidence refreshes.
