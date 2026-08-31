# ADR-0015: Deploy the canonical research service without duplicating compute

- Status: Accepted
- Date: 2026-08-01

## Context

The Sites workspace is deployed on a Cloudflare Worker, while the accepted
backtest boundary is a Go control plane invoking the Python research compute
plane. The deployed workspace currently falls back to `localhost:8080`, so a
browser can inspect committed evidence but cannot submit a new backtest unless
the researcher is running the API locally.

Reimplementing the strategies and portfolio accounting in TypeScript would make
the hosted result convenient at the cost of a second, divergent backtest
engine. Bundling generated market datasets into the frontend would also weaken
the immutable dataset boundary and make ordinary UI releases carry analytical
data.

## Decision

Deploy the existing Go API and Python compute plane together as one stateful
research service. The service image contains:

- the Go API and task orchestrator;
- the pinned Python environment and canonical `quantos` research CLI;
- no market datasets, experiment artifacts, credentials, or generated reports.

The deployment mounts persistent storage for immutable datasets, task records,
experiment artifacts, and intelligence snapshots. Dataset synchronization is an
explicit administrative operation and never runs implicitly when the API
starts. A configured required bundle version is part of readiness: the service
is live before it has data, but it is not ready to accept research traffic until
the exact bundle manifest and writable persistence roots are present.

Runtime configuration may come from flags or `QUANTOS_*` environment variables.
The API exposes liveness at `/healthz` and deployment readiness at `/readyz`.
The browser origin is allow-listed explicitly. The service retains the existing
historical-simulation-only contract and contains no exchange credentials,
orders, paper trading, or live execution endpoints.

The Sites application receives the deployed API origin through
`NEXT_PUBLIC_QUANTOS_API_URL` only after the service has a stable HTTPS URL.
Choosing and provisioning a paid or account-bound container host remains a
human deployment decision.

## Consequences

Positive:

- local and hosted backtests use exactly the same engine and artifact format;
- deployment does not require committing generated datasets or duplicating
  strategy implementations;
- health checks distinguish a running process from a research-ready service;
- persistent Run evidence survives application restarts when the host mounts
  durable storage.

Tradeoffs:

- the service needs a container host with persistent storage and enough memory
  for PyArrow/DuckDB workloads;
- the first deployment is a single instance because the file-backed task store
  is not safe for multiple API replicas;
- initial dataset synchronization remains an explicit, potentially long-running
  administrative step;
- the frontend cannot be connected until a stable service URL and deployment
  owner are chosen.
