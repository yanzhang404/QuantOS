# API App

Future Go composition root for the platform API and orchestration modules.

The first implementation increment consumes
`packages/api-schema/schemas/backtest.v1.schema.json` and will expose strategy,
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
- `GET /api/v1/strategies`
- `POST /api/v1/backtests`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/experiments/{run_id}`

Task metadata is stored as atomic JSON files. The API resolves dataset paths
from the configured trusted data root; requests cannot choose local paths or
commands. One background worker runs historical simulations through the Python
CLI and links successful Tasks to deterministic Run IDs.

Experiment detail is read-only. It normalizes the selected Run's metrics,
fills, equity, position, and running drawdown from bounded immutable artifacts;
the browser never receives local artifact paths.

This local file store supports one API process. PostgreSQL replaces it before
multi-user or multi-process operation.
