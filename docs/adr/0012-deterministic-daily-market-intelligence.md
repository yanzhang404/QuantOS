# ADR-0012: Separate deterministic sentiment scoring from agent-authored daily intelligence

- Status: Accepted
- Date: 2026-08-01

## Context

QuantOS needs a daily market brief and a homepage sentiment indicator derived
from news, options, volatility, perpetual-futures positioning, momentum,
liquidations, breadth, and macro-risk inputs. A language model can classify and
summarize news, but allowing it to invent the numerical index would make the
result non-reproducible and difficult to audit. External articles can also
contain untrusted or adversarial text.

## Decision

Add a versioned `intelligence.v1` boundary with two records:

- a daily input containing normalized market-factor observations and
  source-linked news classifications;
- an immutable daily snapshot containing the deterministic score, component
  scores, factor contributions, a bounded daily brief, and provenance.

Python under `services/agent` owns validation, deterministic calculation, brief
assembly, and atomic local publication. Go serves only the latest validated
snapshot from a trusted root through `GET /api/v1/intelligence/latest`. The web
workspace may use an explicitly labeled sample snapshot when the local API has
not published live data.

Sentiment methodology `quantos-sentiment-v1.0.0` maps rolling percentiles into
0–100 greed-oriented factor scores. High volatility, defensive option
positioning, and macro stress are inverted. Market sentiment receives 75% of
the composite weight; source-weighted news sentiment receives 25%. Inputs,
weights, directions, timestamps, source URLs, and a SHA-256 identity are stored
with every output.

An agent or OpenClaw workflow may collect, deduplicate, classify, and summarize
news into the input contract. It receives read-only network access to approved
sources and cannot execute commands, access trading credentials, place orders,
or modify the numerical methodology. Agent prose is treated as commentary, not
as a trading signal.

The first local store uses one JSON file per date plus an atomically replaced
`latest.json` pointer. This is consistent with the single-maintainer modular
monolith and can later move to transactional metadata storage without changing
the public contract.

## Consequences

Positive:

- the displayed index is reproducible and independently testable;
- news explanations retain citations and cannot silently alter the score;
- the Agent runtime remains replaceable and can be OpenClaw or another tool;
- homepage consumers receive one small, safe, read-only resource;
- sentiment history can later become a research feature with explicit lineage.

Tradeoffs:

- collectors must normalize market observations to rolling percentiles;
- agent-generated classifications still require source and confidence review;
- the first file store supports one publisher and one latest snapshot;
- a sentiment indicator is contextual research data, not evidence of alpha.
