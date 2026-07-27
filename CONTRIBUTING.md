# Contributing

## Principles

- Keep changes small enough to review and reproduce.
- Update documentation with behavior and contract changes.
- Prefer explicit module boundaries over shared mutable internals.
- Add tests for critical domain behavior and regressions.
- Never commit credentials, private keys, account data, or production endpoints.

## Development workflow

1. Read `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, and relevant ADRs.
2. Create a focused branch from `main`.
3. Write or update tests alongside implementation.
4. Run `./scripts/validate_structure.sh` and module-specific checks.
5. Use a concise imperative commit message.
6. Open a pull request describing scope, decisions, tests, and risks.

## Commit convention

Use a short imperative summary, optionally prefixed by the area:

```text
docs: define experiment reproducibility contract
data: validate Kline interval continuity
backtest: apply fees to fill events
```

Do not mix formatting, refactoring, and behavior changes without a clear reason.

## Architecture decisions

Create an ADR in `docs/adr/` when a choice changes system boundaries, data
formats, major dependencies, safety policy, or a decision that will be expensive
to reverse. Accepted ADRs are immutable; supersede them with a new record.

## Definition of done

- Acceptance behavior is documented.
- Automated tests cover critical behavior.
- Static, unit, and integration checks pass.
- Data and experiment outputs are reproducible.
- No secret or live-trading capability is introduced.
