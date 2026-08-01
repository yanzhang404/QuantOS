# ADR-0018: Separate Agent proposals, evidence attachment, and human promotion

- Status: Accepted
- Date: 2026-08-01

## Context

QuantOS needs a repeatable way for an Agent to suggest new strategies without
allowing generated prose, code, or a favorable backtest to silently enter the
approved Strategy Library. Candidate records must also distinguish a promising
hypothesis from implemented code and independently reproducible evidence.

## Decision

Introduce a bounded `candidate-proposal.v1` input and a durable
`candidate-record.v1` lifecycle:

```text
proposed → implemented → review_ready → approved
        ↘ rejected     ↘ rejected   ↗
```

- An Agent may create `proposed` records containing a short hypothesis,
  manifest-shaped parameters, supported intervals, implementation and research
  plans, and a bounded list of public HTTPS sources.
- Proposal inputs cannot contain source code, shell commands, filesystem paths,
  credentials, order instructions, or arbitrary extra fields.
- `implemented` requires a repository-owned implementation reference and named
  deterministic test evidence. It does not claim the strategy works.
- `review_ready` requires a real `robustness-review.v1` artifact whose strategy
  slug matches the proposal and whose overall gate and every component gate
  pass. The transition records the immutable review ID and file digest; a caller
  cannot provide a boolean substitute or reuse another strategy's evidence.
- `approved` and `rejected` require an explicit human actor and rationale.
  Agents and system actors cannot make the promotion decision.
- Every transition is appended with actor kind, timestamp, evidence identity,
  and rationale. Records are atomically replaced under a single-process local
  store; proposal identity remains content-addressed.
- The API and workspace expose candidate records read-only. Lifecycle mutations
  remain deliberate CLI operations until authenticated human identities exist.

Approval changes candidate research state only. Registering executable code in
the Strategy Library remains a reviewed repository change; no lifecycle action
can place orders or enable paper/live trading.

## Consequences

Positive:

- Agent discovery becomes auditable and structurally bounded;
- favorable prose cannot masquerade as reproducible evidence;
- approval authority remains explicit and human;
- candidate history can later move to transactional storage without changing
  the lifecycle contract.

Tradeoffs:

- transitions require CLI access;
- the current EMA-only robustness runner cannot validate arbitrary new strategy
  implementations until strategy-specific robustness adapters are added;
- an approved candidate still needs a reviewed catalog/code change.
