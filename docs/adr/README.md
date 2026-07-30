# Architecture Decision Records

ADRs capture consequential decisions and their tradeoffs. Use the template below
and allocate the next four-digit sequence number.

```text
# ADR-NNNN: Decision title
Status: Proposed | Accepted | Superseded
Date: YYYY-MM-DD

## Context
## Decision
## Consequences
```

Accepted decisions:

- [ADR-0001: Start with a modular monolith](0001-modular-monolith.md)
- [ADR-0002: Split platform and research responsibilities between Go and Python](0002-go-python-boundary.md)
- [ADR-0003: Store historical analytical data in Parquet and query it with DuckDB](0003-parquet-duckdb.md)
- [ADR-0004: Execute close-generated signals at the next Kline open](0004-next-bar-open-execution.md)
- [ADR-0005: Select parameters chronologically before holdout evaluation](0005-chronological-out-of-sample-selection.md)
- [ADR-0006: Start the product workspace as a read-only research view](0006-read-only-research-workspace.md)
- [ADR-0007: Derive a compact strategy visualization artifact](0007-strategy-visualization-artifact.md)
- [ADR-0008: Version backtest orchestration contracts independently](0008-versioned-backtest-orchestration-contract.md)
- [ADR-0009: Persist local backtest tasks as atomic JSON records](0009-file-backed-local-task-orchestration.md)
- [ADR-0010: Serve experiment visualization as a derived read model](0010-experiment-visualization-read-model.md)
- [ADR-0011: Separate strategy library from research lifecycle](0011-strategy-library-and-research-lifecycle.md)
