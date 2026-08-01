# API App

Go composition root for the platform API and research orchestration modules.

The API consumes
`packages/api-schema/schemas/backtest.v1.schema.json` and exposes strategy,
backtest submission, task, and experiment resources. It owns idempotency and
task lifecycle; Python remains responsible for deterministic research compute.

## Local API

```bash
go run ./apps/api/cmd/quantos-api \
  -data-root data \
  -artifact-root artifacts/experiments \
  -state-root var/quantos/tasks
```

The server listens on `127.0.0.1:8080` by default and exposes:

- `GET /healthz`
- `GET /readyz`
- `GET /api/v1/strategies`
- `POST /api/v1/backtests`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/experiments`
- `GET /api/v1/experiments/{run_id}`
- `PUT /api/v1/experiment-archives/{run_id}`
- `DELETE /api/v1/experiment-archives/{run_id}`
- `GET /api/v1/intelligence/latest`

Task metadata is stored as atomic JSON files. The API first verifies that a
submitted dataset identity belongs to its immutable Bundle, then resolves the
dataset path from the configured trusted data root; requests cannot choose
local paths or commands. One background worker runs historical simulations
through the Python CLI and links successful Tasks to deterministic Run IDs.

Experiment detail is read-only. It normalizes the selected Run's metrics,
bars, fills, equity, position, and running drawdown from bounded immutable artifacts;
the browser never receives local artifact paths.

Experiment listing returns at most 200 validated summaries and supports exact
symbol, interval, strategy, and archive-state filters. Archive operations write
only a reversible marker below the Task state root; they never change or remove
the immutable Run directory.

This local file store supports one API process. PostgreSQL replaces it before
multi-user or multi-process operation.

## Production container

The production image packages this Go API together with the locked Python
research environment. It deliberately contains no datasets or generated Run
artifacts. Mount `/var/lib/quantos` on persistent storage and configure:

- `QUANTOS_ALLOWED_ORIGIN`: exact HTTPS workspace origin;
- `QUANTOS_REQUIRED_BUNDLE`: optional 16-character bundle version required by
  `/readyz`;
- `QUANTOS_DATA_ROOT`, `QUANTOS_ARTIFACT_ROOT`, `QUANTOS_STATE_ROOT`, and
  `QUANTOS_INTELLIGENCE_ROOT`: persistent paths when the defaults are unsuitable;
- `PORT` or `QUANTOS_LISTEN`: host-assigned network binding;
- `QUANTOS_QUEUE_SIZE`: bounded in-process task queue size.

`/healthz` proves the process is alive. `/readyz` additionally checks the
configured roots, Python runner, and required immutable Bundle. Startup never
downloads data. Run synchronization as an explicit administrative job before
directing browser traffic to a fresh volume.

For local container validation:

```bash
docker compose --profile research up --build research-api
```

This service must remain a single replica while Tasks use atomic JSON files.
See [ADR-0015](../../docs/adr/0015-deploy-canonical-research-service.md).

Daily intelligence is read-only and loaded from
`var/quantos/intelligence/latest.json` by default. Publish it through the
validated Python workflow; the API rejects symlinks, oversized files, unknown
fields, invalid sources, and scores that do not match the fixed methodology.
