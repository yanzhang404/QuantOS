# API

The future Go control plane exposes project, dataset, strategy, backtest,
experiment, and task resources. Contracts are versioned, observable, and
independent of module-internal persistence models.

## Backtest v1 boundary

The normative language-neutral schema is
`packages/api-schema/schemas/backtest.v1.schema.json`. Its first endpoints are:

| Method | Resource | Result |
| --- | --- | --- |
| `GET` | `/api/v1/strategies` | Editable built-in strategy definitions |
| `POST` | `/api/v1/backtests` | Accept a historical backtest and return a Task |
| `GET` | `/api/v1/tasks/{task_id}` | Read task state and resulting Run ID |
| `GET` | `/api/v1/experiments/{run_id}` | Read one reproducible experiment and its chart series |
| `GET` | `/api/v1/experiments` | Filter saved completed experiments (planned) |
| `GET` | `/api/v1/intelligence/latest` | Read the latest validated daily brief and sentiment snapshot |

Submitting the same HTTP request twice with one idempotency key returns the same
Task. Submitting identical deterministic inputs with a new idempotency key
creates a new Task that may reuse the existing Run ID.

## Required submission identity

A submission records:

- immutable dataset version and SHA-256 content identity;
- symbol, interval, and optional bounded evaluation range;
- strategy name, version, and validated parameters;
- initial cash, fees, slippage, maximum exposure, and final-liquidation policy;
- an optional human label and note.

Dataset intervals use the shared `5m`, `15m`, `1h`, `4h`, or `1d` vocabulary.
Submission still fails when the referenced immutable dataset version is not
present beneath the trusted data root.

Strategy discovery returns a manifest for every executable strategy: category,
lifecycle stage, implementation reference, supported intervals, and parameter
specifications. The web client renders editable fields from this catalog.

The request never accepts dataset paths, experiment output paths, shell
commands, exchange credentials, or live-execution controls.

## Task and experiment distinction

A Task is one user submission and has operational state. An Experiment is one
content-addressed deterministic result. A successful Task points to a Run ID
and states whether the existing experiment was reused.

The first API increment is historical research only. Live and paper trading
remain outside this contract.

## Implemented local task service

The first Go service implements strategy discovery, submission, task lookup,
and task history. It persists one atomic JSON record per Task and runs one
background Python worker. Accepted tasks use these transitions:

```text
queued → running → succeeded
                 ↘ failed
queued/running + service restart → failed(service_restarted, retryable)
```

Completed Python experiment directories remain the Run source of truth. The
implemented Experiment detail resource derives normalized metrics, fills,
equity, position, and drawdown from those immutable artifacts. Experiment
listing and comparison are the next API increments.
