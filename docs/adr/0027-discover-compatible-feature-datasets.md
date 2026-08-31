# ADR-0027: Discover only compatible external feature datasets

- Status: Accepted
- Date: 2026-08-02

## Context

ADR-0026 removed client-supplied paths, but requiring a researcher to copy an
opaque version string is still error-prone. A global list of feature versions
would be worse: it could suggest a dataset aligned against another symbol,
timeframe, or immutable Spot parent, and the request would fail only after
submission.

## Decision

Add a bounded read-only feature-dataset catalog to the Go API. A query must
identify the supported feature series plus the exact Spot symbol, interval,
dataset version, and content hash. The catalog scans only the canonical trusted
data-root directory for that identity, ignores malformed or incomplete entries,
and returns at most 100 validated manifests ordered newest first.

The workspace requests the catalog when an external-feature strategy is
selected. It renders compatible versions as a selector with matched, stale, and
no-prior counts. It automatically selects the newest compatible version but
submits the exact version value. When none exists, the Run action is disabled
with an explicit availability message; the client never creates sample feature
data or falls back to an incompatible version.

## Consequences

- researchers choose from evidence the server can actually execute;
- compatibility failures move from asynchronous worker errors to a visible
  pre-submission state;
- the selected immutable version remains part of request and Run identity;
- catalog discovery stays read-only and performs no collection or mutation.
