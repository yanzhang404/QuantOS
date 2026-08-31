# ADR-0020: Build daily intelligence inputs from allow-listed public endpoints

- Status: Accepted
- Date: 2026-08-01

## Context

The homepage currently falls back to a visibly labeled sample sentiment input.
Current daily publication needs real observations without API keys, account
data, article-body scraping, hidden network calls, or Agent control over the
fixed scoring methodology. Several factors do not provide a free historical
percentile series, so their calibration must accumulate reproducibly over time.

## Decision

Add a bounded public collector that creates `intelligence.v1` input only:

- HTTPS hosts and endpoint paths are explicitly allow-listed;
- requests use fixed timeouts, response-size limits, a descriptive user agent,
  and no credentials or caller-supplied URLs;
- Binance Spot provides BTC momentum and a fixed-liquid-universe breadth share;
- Binance Futures provides BTC funding and taker buy/sell imbalance, with the
  latter explicitly labeled as a liquidation-pressure proxy;
- Deribit provides BTC DVOL and option put/call open-interest ratio;
- Cboe's public daily VIX history provides the macro-risk observation;
- CoinDesk's public RSS feed contributes headline metadata only. Article bodies
  are not fetched or stored;
- news classification uses a versioned, low-confidence title lexicon. It is
  context, not a market or profitability claim;
- each factor's raw daily value, unit, source, and observation time are stored
  in a bounded local history and converted to an inclusive empirical percentile
  after 30 observations;
- the first complete seven-factor batch for a UTC date is atomically pinned;
  retries reuse it even if an intraday public value has moved;
- before every factor has 30 observations, the input is marked `partial` and
  uses neutral percentile `0.5` for under-calibrated factors;
- collection and deterministic scoring/publication remain separate commands.

The collector uses public read-only market-data endpoints. It cannot access an
account, place orders, change index weights, or enable paper/live trading.

## Consequences

Positive:

- the homepage can progress from illustrative fixtures to attributable current
  inputs;
- every observation and source remains inspectable;
- unavailable or immature inputs degrade visibly to `partial` instead of being
  fabricated;
- future Agent summaries reuse the same bounded input contract.

Tradeoffs:

- the first 29 successful daily collections remain neutrally calibrated;
- taker imbalance is only a liquidation-pressure proxy;
- headline lexicon sentiment is intentionally weak and can miss nuance;
- endpoint maintenance requires explicit code and contract updates.
