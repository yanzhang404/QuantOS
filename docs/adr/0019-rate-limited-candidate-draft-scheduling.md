# ADR-0019: Rate-limit candidate discovery and prepare review-only draft packages

- Status: Accepted
- Date: 2026-08-01

## Context

An Agent that can continuously suggest strategies can easily create more noise
than research value. Automatically opening many branches or pull requests also
creates external state before a researcher has inspected the hypothesis. The
accepted roadmap limits discovery to one or two explainable candidates per week
and requires every candidate to enter the guarded lifecycle.

## Decision

Introduce a deterministic `candidate-draft.v1` package prepared from an existing
`proposed` candidate record:

- weeks use UTC ISO week identity and contain at most two prepared drafts;
- a caller may lower the weekly limit to one but cannot raise it above two;
- the same content-addressed proposal can be scheduled only once;
- scheduling accepts only proposals with at most six editable parameters and
  three supported intervals so the first research question stays explainable;
- the package copies the immutable proposal, records its slot and timestamp,
  and generates a review-oriented Markdown pull-request body and checklist;
- package publication is atomic and contains no generated strategy code,
  command, credential, dataset, or favorable-result claim;
- preparation performs no network call and does not create a Git branch or pull
  request. A human may later use the package to open a draft PR deliberately.

The initial atomic file store is a single-process boundary. A transactional
lease replaces it before multiple schedulers can run concurrently.

The scheduler cannot mark implementation, attach evidence, approve a candidate,
register a strategy, or enable paper/live trading.

## Consequences

Positive:

- continuous discovery has a hard, testable attention budget;
- every suggested strategy arrives with the same review structure;
- rejected or deferred ideas do not create remote repository clutter;
- later GitHub integration can consume the package without changing scheduling
  identity or lifecycle authority.

Tradeoffs:

- remote draft-PR creation remains a deliberate follow-up;
- the scheduler does not rank expected profitability;
- complex strategies must first be simplified into a bounded hypothesis.
