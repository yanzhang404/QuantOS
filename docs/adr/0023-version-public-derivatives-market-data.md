# ADR-0023: Store funding and open-interest histories as separate immutable datasets

- Status: Accepted
- Date: 2026-08-02

## Context

Funding and open interest can add derivatives-positioning context to strategy
research, but they have different timestamps, units, update frequencies, and
retention limits from Spot Klines. Joining them implicitly into the existing
OHLCV schema would hide missing observations and encourage lookahead errors.

Binance's public USDⓈ-M Futures API exposes ascending funding history with up to
1,000 records per request. Its open-interest statistics endpoint exposes
period-end quantity and notional value but only for the latest month.

## Decision

Add a `derivatives-market.v1` immutable dataset family with two typed records:

- funding observations: symbol, funding time, funding rate, optional mark price,
  and rate type;
- open-interest observations: symbol, period, period-end time, contract
  quantity, and USDT notional value.

The downloader uses only the two allow-listed public GET endpoints, explicit
UTC bounds, fixed limits/timeouts, ascending pagination, and no credentials.
Storage validates finite decimals, supported BTCUSDT/ETHUSDT symbols, supported
periods, strict timestamp ordering, uniqueness, requested coverage, and content
SHA-256 before atomically publishing Parquet plus a manifest.

Funding and open interest remain separate datasets and are not automatically
joined to Klines. A later feature must declare its alignment rule explicitly;
only observations available at or before a closed Kline may be used. The open
interest manifest records the public one-month source limitation rather than
claiming unavailable history.

## Consequences

Positive:

- derivatives inputs become reproducible and independently inspectable;
- the platform cannot silently forward-fill them into Spot data;
- source retention limits and real gaps remain visible;
- future funding/OI features can name exact dataset versions.

Tradeoffs:

- initial open-interest research is limited to roughly one month;
- longer OI history must accumulate prospectively or use a separately reviewed
  provider;
- no strategy consumes the new data until an explicit point-in-time join is
  implemented and tested.

## References

- [Binance USD-M Futures market-data catalog: funding-rate history](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#get-funding-rate-history)
- [Binance USD-M Futures market-data catalog: open-interest statistics](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#open-interest-statistics)
