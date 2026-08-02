# ADR-0021: Refresh daily intelligence as an observable single-writer job

- Status: Accepted
- Date: 2026-08-02

## Context

Public collectors and deterministic publication now work, but two manual
commands do not provide reliable daily operation. Overlapping scheduler runs
could race on calibration history, and a failed collection must never replace
the last valid homepage snapshot. Operators also need to distinguish a current
publication from a stale or repeatedly failing job.

## Decision

Add one `quantos intelligence refresh` command that:

- acquires a non-blocking OS file lock before any network or state mutation;
- collects and validates one UTC daily input, then publishes it with the fixed
  scoring methodology;
- retains dated validated inputs and the existing immutable daily snapshots;
- never changes `latest.json` when collection, validation, or publication fails;
- atomically records a bounded `refresh-health.v1` document containing the
  current state, last attempt, last success, consecutive failure count, and a
  fixed error code without stack traces or endpoint response content;
- exposes that document through a read-only Go endpoint, which derives `stale`
  when no successful refresh occurred in the last 36 hours;
- runs only when invoked by an external scheduler. API startup performs no
  hidden network calls.

The deployment supplies a one-shot Compose service and a persistent systemd
timer scheduled after the UTC daily close. The service remains single-writer;
the file lock is still mandatory because timers and manual retries may overlap.

## Consequences

Positive:

- daily refresh becomes one idempotent operational command;
- a public-source outage leaves the previous valid snapshot available;
- the homepage can show current, stale, or failed refresh state explicitly;
- operators can retry safely without corrupting daily calibration.

Tradeoffs:

- the lock relies on Unix `flock`, matching the supported macOS/Linux research
  environments;
- a crashed process may leave a `running` health record, but the OS releases
  the lock and the next scheduled attempt can recover it;
- the scheduler must run on the stateful service host and preserve `var/`.
