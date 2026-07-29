# Donchian ATR Strategy Study

## Status

Completed on 2026-07-29. The protocol and parameters below were fixed before
the evaluation data was downloaded. Structured results are stored in
[`examples/backtest/donchian-atr-study/results.json`](../../examples/backtest/donchian-atr-study/results.json).

## Hypothesis

A long-only Donchian breakout with ATR volatility targeting can reduce maximum
drawdown and improve risk-adjusted performance relative to passive buy and hold
on liquid crypto markets, after explicit fees and slippage. It may underperform
in absolute return during persistent bull markets.

## Markets and periods

- Markets: Binance Spot BTCUSDT and ETHUSDT.
- Interval: 4h.
- Development observation period: 2022-01-01 through 2024-12-31 UTC.
- Fixed evaluation period: 2025-01-01 through 2026-06-30 UTC.
- Data intervals are half-open and end at 2026-07-01T00:00:00Z.

The evaluation period must not be used to change strategy rules or parameters
in this study.

## Predeclared strategies

1. Buy and hold at 100% maximum exposure.
2. EMA cross with fast period 20 and slow period 50.
3. Donchian ATR with:
   - entry period 55;
   - exit period 20;
   - ATR period 20;
   - target annual volatility 20%;
   - maximum exposure 100%;
   - rebalance threshold 5%.

All strategies start with 100,000 USDT, execute close-generated signals at the
next open, pay 10 bps per fill plus 5 bps adverse slippage, remain long-only,
and liquidate at the final boundary.

## Evaluation

For each market and period, record total return, Sharpe ratio, maximum drawdown,
completed trades, fills, and fees. Repeat Donchian ATR on the evaluation period
with doubled fees and slippage.

The hypothesis is supported only if the strategy's drawdown and Sharpe behavior
is directionally better than buy and hold across both assets. A result from one
asset alone is not treated as general evidence. Low trade count, strong
development-to-evaluation degradation, or cost sensitivity must be called out.

## Results

Development period:

| Market | Strategy | Return | Sharpe | Max drawdown | Trades |
| --- | --- | ---: | ---: | ---: | ---: |
| BTC | Buy and hold | 99.29% | 0.701 | 67.21% | 1 |
| BTC | EMA cross | 64.45% | 0.653 | 47.80% | 58 |
| BTC | Donchian ATR | 24.67% | 0.874 | 9.57% | 163 |
| ETH | Buy and hold | -10.64% | 0.274 | 76.23% | 1 |
| ETH | EMA cross | -0.83% | 0.204 | 44.40% | 63 |
| ETH | Donchian ATR | 8.46% | 0.353 | 16.04% | 112 |

Fixed evaluation period:

| Market | Strategy | Return | Sharpe | Max drawdown | Trades |
| --- | --- | ---: | ---: | ---: | ---: |
| BTC | Buy and hold | -37.71% | -0.492 | 53.45% | 1 |
| BTC | EMA cross | -10.67% | -0.172 | 30.07% | 30 |
| BTC | Donchian ATR | -0.33% | 0.012 | 9.44% | 76 |
| BTC | Donchian ATR, 2x costs | -3.88% | -0.291 | 10.89% | 76 |
| ETH | Buy and hold | -53.29% | -0.397 | 68.03% | 1 |
| ETH | EMA cross | -30.68% | -0.419 | 51.66% | 34 |
| ETH | Donchian ATR | 5.18% | 0.462 | 9.10% | 42 |
| ETH | Donchian ATR, 2x costs | 3.35% | 0.315 | 10.12% | 42 |

## Conclusion

The result supports the narrow risk-control hypothesis: Donchian ATR produced
materially lower drawdown and better Sharpe behavior than buy and hold on both
evaluation assets. It does not support a broad high-return claim. BTC was
approximately flat after normal costs and negative under doubled costs, while
ETH produced a modest positive return.

The strategy also generated many more fills than the baselines. Cost sensitivity,
especially on BTC, is the primary follow-up risk. No parameters were changed
after observing evaluation results. These two assets and one interval are not
enough evidence for production or live trading.

## Reproduction

Dataset versions:

| Dataset | Version | Rows |
| --- | --- | ---: |
| BTC development | `60d1e40505ad1fb2` | 6,576 |
| BTC evaluation | `024f23d9a629502e` | 3,276 |
| ETH development | `9d5fc0adea940804` | 6,576 |
| ETH evaluation | `4490813e551e1eaa` | 3,276 |

Representative command:

```bash
uv run quantos backtest run \
  --dataset "<dataset-version-path>" \
  --strategy donchian-atr \
  --entry-period 55 \
  --exit-period 20 \
  --atr-period 20 \
  --target-annual-volatility 0.20 \
  --rebalance-threshold 0.05 \
  --initial-cash 100000 \
  --fee-bps 10 \
  --slippage-bps 5
```

Every Run ID and full dataset content hash is recorded in the structured results
artifact. Generated Parquet data and full experiment directories stay outside
Git.
