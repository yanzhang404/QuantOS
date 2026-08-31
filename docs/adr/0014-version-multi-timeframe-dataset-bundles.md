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

Current-data synchronization uses the latest fully closed boundary shared by
the complete matrix. Because the matrix contains `1d`, this is the current UTC
midnight boundary; data ending at that boundary contains the daily candle that
opened one day earlier and no incomplete daily candle. The command discovers a
verified bundle with the requested historical start, downloads only each
member's missing tail, combines it with the prior immutable dataset, validates
the full range, and publishes new dataset and bundle versions. It never mutates
the source bundle or its members.

Binance maintenance windows can omit expected intervals or shorten the reported
close time of the final bar before a halt. QuantOS preserves that source truth:
open times must remain aligned, unique, ordered, and reach both requested range
boundaries, while missing intervals are counted in dataset and coverage
evidence. The ingestion layer never synthesizes prices or volume to hide a
source gap.

If no compatible source bundle exists, current-data synchronization performs a
full historical backfill. If the source already ends at the target boundary,
the operation is a no-op and returns the same bundle identity. A failed member
may leave reusable content-addressed dataset versions below the ignored data
root, but it cannot publish a partial bundle or coverage claim.

Generated Parquet data and local bundle manifests stay below the ignored data
root. A compact, repository-owned coverage evidence file may be exported from a
verified bundle for the product workspace. That evidence records the bundle
version, range, member dataset versions, row counts, and validation status; it
does not replace the source manifests or contain market rows.

Backtest submissions identify a specific bundle version plus one symbol and
interval member. The control plane verifies that the submitted dataset version
and content hash are an exact member of that bundle before resolving its trusted
local path. Tasks retain the bundle identity, and Runs retain the resolved
immutable dataset identity and evaluation range. Execution must never resolve
“latest”; the workspace may choose the current bundle only before submission.

## Consequences

Positive:

- the ten-cell product coverage matrix is backed by real verified datasets;
- one bundle version can be attached to a research review or Run group;
- partial downloads cannot be mistaken for a complete research input set;
- repeated synchronization produces the same identity for the same normalized
  rows and range;
- daily refreshes transfer only missing Klines after the first backfill;
- every refresh retains the prior bundle as reproducible Run evidence;
- no authenticated exchange or trading capability is introduced.

Tradeoffs:

- a failed member prevents bundle publication even if nine datasets succeeded;
- the initial common range must align to every requested interval, which means
  day boundaries when `1d` is included;
- local data storage grows materially for long `5m` ranges;
- extending a dataset currently revalidates and republishes its complete
  normalized history, trading local compute for a simple deterministic contract;
- coverage evidence is a compact projection and must always retain its source
  bundle identity.
