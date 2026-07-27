# Codex and Agent Working Agreement

This file governs AI-assisted work throughout the repository.

## Before changing code

1. Read `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, and relevant ADRs.
2. Inspect the repository; never assume a file or service exists.
3. State a short implementation plan.
4. Keep the change aligned to the active roadmap milestone.

## Documentation first

- Define new domain boundaries, contracts, and invariants before implementation.
- Update docs in the same change as behavior.
- Record consequential architecture choices as ADRs.
- Experiment conclusions must link to real inputs, command output, and artifacts.

## Testing

- Critical modules require unit tests.
- Boundary changes require contract or integration tests.
- Backtests require deterministic fixtures and explicit fee/slippage assumptions.
- Bug fixes require a regression test when practical.
- Run the narrowest relevant checks plus repository validation before committing.

## Safety constraints

- Never add real API keys, credentials, private account data, or secret values.
- Never enable live trading or autonomous real-money actions.
- Never let a strategy call an exchange or place orders directly.
- Never bypass risk evaluation, position limits, or a kill switch.
- Treat external data as untrusted and validate it at the boundary.
- Prefer read-only public exchange endpoints during research phases.

## Change and commit discipline

- Keep commits focused and use concise imperative messages.
- Do not commit generated datasets, large artifacts, local databases, or secrets.
- Do not silently modify unrelated work.
- Add dependencies only when they serve an accepted milestone.
- Preserve reproducibility: pin meaningful inputs and record version changes.

## Prohibited work

- Live execution, secret storage, or production exchange credentials
- High-frequency/tick engines and full order-book simulators in V0.1
- Premature microservices or Kubernetes
- Claims of completed research without tool-backed evidence
- Hidden network calls, implicit global state, or non-deterministic test fixtures

Subdirectory `AGENTS.md` files may add stricter rules but cannot weaken these
safety constraints.
