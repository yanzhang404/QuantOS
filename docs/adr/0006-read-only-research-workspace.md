# ADR-0006: Start the product workspace as a read-only research view

- Status: Accepted
- Date: 2026-07-29

## Context

QuantOS now has reproducible datasets, backtests, strategy studies, cost stress
tests, and structured artifacts, but those results require command-line and
file-level inspection. A product surface is useful only if it presents real
evidence without introducing premature orchestration, authentication, mutable
state, or trading actions.

## Decision

The first product workspace is a read-only Next.js application under
`apps/web`, built with vinext for Cloudflare Workers and deployed through Sites.
It consumes the committed Donchian ATR structured result artifact at build time
and exposes:

- market and observation-window filtering;
- strategy return, Sharpe, drawdown, trade, fill, and fee comparison;
- doubled-cost stress results;
- research findings and immutable dataset/Run identities.

The UI contains no order entry, exchange credentials, live data, mutable
research records, or trading activation. A future versioned read-only API will
replace the build-time artifact import when multiple studies and local
experiment directories need browsing.

## Consequences

Positive:

- the implemented research loop becomes visible and usable immediately;
- every displayed number remains grounded in a committed reproducible artifact;
- the product can validate information architecture before API orchestration;
- the safety boundary is explicit: research only, live trading disabled.

Tradeoffs:

- new experiment artifacts require a rebuild before they appear;
- the first workspace contains one study rather than a general artifact browser;
- Next.js and Cloudflare Worker dependencies add a separate frontend toolchain;
- task execution, progress streaming, and user-specific state remain deferred.
