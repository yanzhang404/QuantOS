# Event Schema

Defines immutable, versioned Market, Signal, Risk, Order, Fill, Portfolio, and
Metric events in `quantos_events`. Events carry decisions and observations
between modules without exposing mutable portfolio or exchange state.

`MarketEvent` may carry immutable `FeatureObservation` values pinned to one
feature-dataset version. The engine owns their clock and a strategy cannot
request a future observation.
