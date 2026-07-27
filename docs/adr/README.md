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
