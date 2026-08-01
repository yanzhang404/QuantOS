"""Exchange-neutral Kline contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from enum import StrEnum
from typing import Any, ClassVar

from .errors import ConfigurationError, DownloadError


class Interval(StrEnum):
    """Kline intervals supported by the product contract."""

    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"

    @property
    def milliseconds(self) -> int:
        return {
            Interval.FIVE_MINUTES: 5 * 60 * 1_000,
            Interval.FIFTEEN_MINUTES: 15 * 60 * 1_000,
            Interval.ONE_HOUR: 60 * 60 * 1_000,
            Interval.FOUR_HOURS: 4 * 60 * 60 * 1_000,
            Interval.ONE_DAY: 24 * 60 * 60 * 1_000,
        }[self]

    @classmethod
    def parse(cls, value: str) -> Interval:
        try:
            return cls(value)
        except ValueError as exc:
            supported = ", ".join(item.value for item in cls)
            raise ConfigurationError(
                f"unsupported interval {value!r}; expected one of: {supported}"
            ) from exc


SUPPORTED_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT"})
DECIMAL_QUANTUM = Decimal("0.000000000000000001")


def normalize_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:
        supported = ", ".join(sorted(SUPPORTED_SYMBOLS))
        raise ConfigurationError(f"unsupported symbol {value!r}; expected one of: {supported}")
    return symbol


def datetime_to_milliseconds(value: datetime) -> int:
    if value.tzinfo is None:
        raise ConfigurationError("timestamps must include a timezone")
    return int(value.astimezone(UTC).timestamp() * 1_000)


def milliseconds_to_datetime(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1_000, tz=UTC)


@dataclass(frozen=True, slots=True)
class Kline:
    """One normalized, closed spot-market candlestick."""

    exchange: str
    symbol: str
    interval: Interval
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal

    SCHEMA_VERSION: ClassVar[str] = "kline.v1"

    @classmethod
    def from_binance_row(cls, symbol: str, interval: Interval, row: list[Any]) -> Kline:
        if len(row) < 11:
            raise DownloadError(f"Binance Kline row has {len(row)} fields; expected at least 11")
        try:
            return cls(
                exchange="binance",
                symbol=normalize_symbol(symbol),
                interval=interval,
                open_time=milliseconds_to_datetime(int(row[0])),
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
                volume=Decimal(str(row[5])),
                close_time=milliseconds_to_datetime(int(row[6])),
                quote_volume=Decimal(str(row[7])),
                trade_count=int(row[8]),
                taker_buy_base_volume=Decimal(str(row[9])),
                taker_buy_quote_volume=Decimal(str(row[10])),
            )
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise DownloadError(f"invalid Binance Kline row: {row!r}") from exc

    def canonical_values(self) -> list[str | int]:
        """Return stable values used by the content hash."""

        return [
            self.exchange,
            self.symbol,
            self.interval.value,
            datetime_to_milliseconds(self.open_time),
            datetime_to_milliseconds(self.close_time),
            _decimal_string(self.open),
            _decimal_string(self.high),
            _decimal_string(self.low),
            _decimal_string(self.close),
            _decimal_string(self.volume),
            _decimal_string(self.quote_volume),
            self.trade_count,
            _decimal_string(self.taker_buy_base_volume),
            _decimal_string(self.taker_buy_quote_volume),
        ]


def _decimal_string(value: Decimal) -> str:
    with localcontext() as context:
        context.prec = 38
        return format(value.quantize(DECIMAL_QUANTUM), "f")
