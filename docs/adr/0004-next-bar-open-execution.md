# ADR-0004: Execute close-generated signals at the next Kline open

- Status: Accepted
- Date: 2026-07-27

## Context

A Kline exposes its high, low, close, and final volume only after the interval
closes. A strategy that uses the close to generate a signal cannot also receive
a fill at that same close without assuming information and liquidity that were
not available when the decision was made. That convention creates look-ahead
bias and makes results difficult to reproduce.

## Decision

The V0.1 engine uses these deterministic phases:

1. replay a previously approved target at the current Kline open;
2. apply fixed adverse slippage and proportional fees;
3. update the authoritative portfolio from the resulting fill;
4. publish the closed Kline to the strategy;
5. mark the portfolio at the Kline close;
6. evaluate any new signal through the risk engine;
7. defer an approved target until the next Kline open.

The final pending signal is discarded because no next open exists. By default,
an existing position is forcibly liquidated at the final close with the same fee
and slippage models; runs may explicitly disable that assumption.

## Consequences

Positive:

- strategies cannot trade on a close they only just observed;
- fills, costs, and timestamps are deterministic;
- signal, risk, order, fill, and portfolio responsibilities remain separate;
- the convention can be shared by later paper-trading comparisons.

Tradeoffs:

- gap risk between the signal close and next open is included;
- Kline-level simulation cannot model intrabar order paths or liquidity;
- final liquidation is an artificial experiment boundary and must be reported.

Tick execution, order-book modeling, partial fills, funding, leverage, and short
positions remain outside this milestone.
