# ADR-0014: Version multi-timeframe datasets as atomic research bundles

- Status: Accepted
- Date: 2026-08-01

## Context

QuantOS can already publish one immutable Kline dataset for one symbol and
interval. The product now needs BTCUSDT and ETHUSDT at `5m`, `15m`, `1h`, `4h`,
and `1d`. A strategy Run must not depend on a mutable notion such as “the latest
files in the data directory”, and the workspace must not mark an interval as
available merely because the interval name is supported by code.

Downloading ten independent datasets without a collection identity also makes
it difficult to prove that a coverage display, robustness review, or later
multi-market comparison used one deliberate and complete input set.

## Decision

Introduce an immutable `dataset-bundle.v1` manifest. One bundle identifies an
exact half-open UTC range and contains exactly one verified dataset version for
every requested symbol and interval pair.

The initial product matrix is fixed to:

- symbols: `BTCUSDT`, `ETHUSDT`;
- intervals: `5m`, `15m`, `1h`, `4h`, `1d`;
- source: public, read-only Binance Spot Klines;
- schema: `kline.v1`.

The batch synchronization command downloads and verifies every member before it
publishes the bundle manifest. If any member fails, no bundle is published.
Already published content-addressed datasets may be reused safely. Bundle
identity is a SHA-256 digest over the schema, requested range, and ordered member
identities. Repeating the same synchronization is idempotent.

Generated Parquet data and local bundle manifests stay below the ignored data
root. A compact, repository-owned coverage evidence file may be exported from a
verified bundle for the product workspace. That evidence records the bundle
version, range, member dataset versions, row counts, and validation status; it
does not replace the source manifests or contain market rows.

Backtests continue to accept one explicit immutable dataset path. Later
multi-timeframe or multi-market orchestration must resolve its inputs from a
specific bundle version and persist those resolved dataset identities in the
Run; it must never resolve “latest” during execution.

## Consequences

Positive:

- the ten-cell product coverage matrix is backed by real verified datasets;
- one bundle version can be attached to a research review or Run group;
- partial downloads cannot be mistaken for a complete research input set;
- repeated synchronization produces the same identity for the same normalized
  rows and range;
- no authenticated exchange or trading capability is introduced.

Tradeoffs:

- a failed member prevents bundle publication even if nine datasets succeeded;
- the initial common range must align to every requested interval, which means
  day boundaries when `1d` is included;
- local data storage grows materially for long `5m` ranges;
- coverage evidence is a compact projection and must always retain its source
  bundle identity.
