# Kline Schema v1

`kline.v1` is the normalized, exchange-neutral contract used by the first
market-data and backtest milestones.

| Field | Parquet type | Constraint |
| --- | --- | --- |
| `exchange` | string | `binance` in V0.1 |
| `symbol` | string | `BTCUSDT` or `ETHUSDT` |
| `interval` | string | `5m`, `15m`, `1h`, `4h`, or `1d` |
| `open_time` | timestamp(ms, UTC) | aligned interval start; unique key |
| `close_time` | timestamp(ms, UTC) | next interval start minus 1 ms |
| `open`, `high`, `low`, `close` | decimal(38,18) | positive and internally consistent |
| `volume`, `quote_volume` | decimal(38,18) | non-negative |
| `trade_count` | int64 | non-negative |
| `taker_buy_base_volume` | decimal(38,18) | non-negative |
| `taker_buy_quote_volume` | decimal(38,18) | non-negative |

## Time-range semantics

Download requests use a half-open UTC interval: `start` is inclusive and `end`
is exclusive. Both values must align to the requested Kline interval. The end
must not exceed the latest closed interval boundary, preventing an incomplete
live candle from entering a historical dataset.

## Identity and partitioning

Each published version contains exactly one exchange, market type, symbol, and
interval. The local layout is:

```text
data/market/spot/
  exchange=binance/
    symbol=BTCUSDT/
      interval=1h/
        version=<content-hash>/
          manifest.json
          part-00000.parquet
```

The version is the first 16 hexadecimal characters of a SHA-256 digest over the
schema version and canonical normalized rows. Re-publishing identical rows
returns the existing version rather than mutating it.

## Manifest contract

The manifest records source URL, requested and actual time bounds, schema,
producer version, row count, normalized content hash, validation report, and
the size and SHA-256 checksum of each Parquet file.

## Dataset bundle contract

`dataset-bundle.v1` is a collection manifest over exact `kline.v1` dataset
versions. Members are ordered by symbol and interval and each records its
dataset version, content hash, row count, requested bounds, and local immutable
path. Bundle publication is atomic: every declared member must verify before
the manifest becomes visible.
