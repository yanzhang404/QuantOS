# ADR-0026: Resolve external feature versions at the API boundary

- Status: Accepted
- Date: 2026-08-02

## Context

The first external-feature strategy is executable from the Python CLI, but the
workspace cannot safely submit it. A browser-supplied filesystem path would
couple the product to one machine, expose server layout, and allow a Run to bind
an input outside the trusted immutable data root. Accepting a feature version
without checking its Spot parent could also mix information aligned against a
different price history.

## Decision

Backtest contract v1 accepts an optional `feature_dataset_version` containing
exactly 16 lowercase hexadecimal characters. The field is:

- required for `funding-filtered-ema`;
- forbidden for every strategy that does not consume an external feature;
- resolved by the Go worker beneath the configured immutable data root at the
  canonical funding-alignment location; and
- passed to Python only after its manifest identifies `funding-rate`, the
  `aligned-derivatives.v1` schema, `asof-closed-bar.v1` policy, and the same
  symbol, interval, Spot dataset version, and Spot content hash as the request.

Clients never submit paths. The strategy catalog declares the external-feature
requirement, so the workspace can render a strategy-specific version control
and explain why a Run is unavailable. The experiment read model exposes the
complete v4 feature-dataset lineage already bound into immutable Run artifacts.
Existing submissions and v2/v3 artifacts remain readable.

## Consequences

Positive:

- hosted and local clients share one stable, path-independent contract;
- feature and price histories cannot be combined accidentally;
- ordinary strategies cannot claim unused derivatives inputs;
- the workspace can expose the real candidate without fabricating sample data.

Tradeoffs:

- a feature version must already exist on the research server before submission;
- this increment uses an explicit version field; catalog discovery can be added
  after the hosted server has a durable feature refresh workflow;
- the candidate remains research-only until chronological robustness evidence
  is complete.
