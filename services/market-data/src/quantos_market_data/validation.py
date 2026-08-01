"""Deterministic validation for normalized Klines."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from .errors import ValidationError
from .models import Kline


@dataclass(frozen=True, slots=True)
class ValidationReport:
    row_count: int
    duplicate_count: int
    missing_count: int
    invalid_ohlc_count: int
    invalid_volume_count: int
    invalid_time_count: int
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["errors"] = list(self.errors)
        result["is_valid"] = self.is_valid
        return result

    def raise_if_invalid(self) -> None:
        if not self.is_valid:
            raise ValidationError("; ".join(self.errors))


def validate_klines(
    klines: list[Kline],
    *,
    requested_start: datetime | None = None,
    requested_end: datetime | None = None,
) -> ValidationReport:
    if not klines:
        return ValidationReport(
            row_count=0,
            duplicate_count=0,
            missing_count=0,
            invalid_ohlc_count=0,
            invalid_volume_count=0,
            invalid_time_count=0,
            errors=("dataset contains no Klines",),
        )

    errors: list[str] = []
    first = klines[0]
    expected_delta = timedelta(milliseconds=first.interval.milliseconds)
    expected_close_delta = expected_delta - timedelta(milliseconds=1)

    duplicate_count = 0
    missing_count = 0
    invalid_ohlc_count = 0
    invalid_volume_count = 0
    invalid_time_count = 0
    seen: set[object] = set()
    previous_open = None

    for index, kline in enumerate(klines):
        if (
            kline.exchange != first.exchange
            or kline.symbol != first.symbol
            or kline.interval != first.interval
        ):
            errors.append(f"row {index} does not match dataset identity")

        if kline.open_time in seen:
            duplicate_count += 1
        seen.add(kline.open_time)

        if previous_open is not None:
            delta = kline.open_time - previous_open
            if delta <= timedelta(0):
                errors.append(f"rows are not strictly ordered at index {index}")
            elif delta > expected_delta:
                missing_count += int(delta / expected_delta) - 1
            elif delta != expected_delta:
                errors.append(f"row {index} is not aligned to the expected interval")
        previous_open = kline.open_time

        open_ms = int(kline.open_time.timestamp() * 1_000)
        if (
            open_ms % first.interval.milliseconds
            or kline.close_time < kline.open_time
            or kline.close_time - kline.open_time > expected_close_delta
        ):
            invalid_time_count += 1

        if (
            kline.open <= 0
            or kline.high <= 0
            or kline.low <= 0
            or kline.close <= 0
            or kline.high < max(kline.open, kline.close, kline.low)
            or kline.low > min(kline.open, kline.close, kline.high)
        ):
            invalid_ohlc_count += 1

        if (
            kline.volume < 0
            or kline.quote_volume < 0
            or kline.trade_count < 0
            or kline.taker_buy_base_volume < 0
            or kline.taker_buy_quote_volume < 0
        ):
            invalid_volume_count += 1

    if duplicate_count:
        errors.append(f"found {duplicate_count} duplicate open times")
    if invalid_time_count:
        errors.append(f"found {invalid_time_count} invalid time ranges")
    if invalid_ohlc_count:
        errors.append(f"found {invalid_ohlc_count} invalid OHLC rows")
    if invalid_volume_count:
        errors.append(f"found {invalid_volume_count} invalid volume rows")
    if (requested_start is None) != (requested_end is None):
        errors.append("requested_start and requested_end must be provided together")
    elif requested_start is not None and requested_end is not None:
        if requested_start.tzinfo is None or requested_end.tzinfo is None:
            errors.append("requested range timestamps must include a timezone")
        else:
            normalized_start = requested_start.astimezone(UTC)
            normalized_end = requested_end.astimezone(UTC)
            if normalized_start >= normalized_end:
                errors.append("requested range must be positive")
            elif (
                klines[0].open_time != normalized_start
                or klines[-1].open_time + expected_delta != normalized_end
            ):
                errors.append("dataset does not reach both requested range boundaries")

    return ValidationReport(
        row_count=len(klines),
        duplicate_count=duplicate_count,
        missing_count=missing_count,
        invalid_ohlc_count=invalid_ohlc_count,
        invalid_volume_count=invalid_volume_count,
        invalid_time_count=invalid_time_count,
        errors=tuple(errors),
    )
