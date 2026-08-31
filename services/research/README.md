# Research Service

Owns chronological experiment design, parameter selection, holdout evaluation,
cost stress tests, comparison, automated validity review, and deterministic
promotion gates across time windows, adjacent parameters, costs, and peer
markets. It delegates simulation to `quantos_backtest` and does not own order
execution or lifecycle promotion.

See [`docs/research`](../../docs/research/README.md) and
[ADR-0005](../../docs/adr/0005-chronological-out-of-sample-selection.md).
Robustness gates are defined by
[ADR-0017](../../docs/adr/0017-deterministic-robustness-gates.md).
EMA Cross and Donchian ATR enter that shared runner through the bounded adapter
contract in
[ADR-0029](../../docs/adr/0029-strategy-specific-research-adapters.md).
