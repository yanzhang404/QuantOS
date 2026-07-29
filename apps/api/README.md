# API App

Future Go composition root for the platform API and orchestration modules.

The first implementation increment consumes
`packages/api-schema/schemas/backtest.v1.schema.json` and will expose strategy,
backtest submission, task, and experiment resources. It owns idempotency and
task lifecycle; Python remains responsible for deterministic research compute.
