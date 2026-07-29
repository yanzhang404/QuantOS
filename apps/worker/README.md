# Worker App

The Python CLI is the first historical backtest worker boundary. The Go API
invokes it with a fixed argument array assembled from validated contract v1
fields. The worker:

- verifies the resolved immutable dataset;
- optionally applies a half-open evaluation range;
- constructs one built-in strategy with explicit parameters;
- runs the deterministic engine;
- publishes content-addressed experiment artifacts;
- returns Run ID, reuse state, and metrics as JSON.

Task metadata remains owned by the Go control plane. The Python worker receives
no Task Store access and has no live-execution capability.
