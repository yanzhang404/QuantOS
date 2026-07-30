"""Strict Python implementation of the language-neutral backtest.v1 contract."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Literal

SCHEMA_VERSION = "1.0"
STRATEGY_VERSION = "1.0.0"
StrategyName = Literal["buy-and-hold", "ema-cross", "donchian-atr"]
TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
ParameterValue = int | str

_HEX_16 = re.compile(r"^[0-9a-f]{16}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL = re.compile(r"^[A-Z0-9]{5,20}$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_TASK_ID = re.compile(r"^task_[0-9a-f]{16}$")
_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


class ContractValidationError(ValueError):
    """Raised when untrusted API input violates the versioned contract."""


@dataclass(frozen=True, slots=True)
class DatasetRef:
    version: str
    content_sha256: str
    symbol: str
    interval: Literal["5m", "15m", "1h", "4h", "1d"]
    data_start: datetime | None = None
    data_end: datetime | None = None

    def __post_init__(self) -> None:
        if not _HEX_16.fullmatch(self.version):
            raise ContractValidationError("dataset version must be 16 lowercase hex characters")
        if not _HEX_64.fullmatch(self.content_sha256):
            raise ContractValidationError(
                "dataset content_sha256 must be 64 lowercase hex characters"
            )
        if not _SYMBOL.fullmatch(self.symbol):
            raise ContractValidationError("dataset symbol must be uppercase alphanumeric")
        if self.interval not in {"5m", "15m", "1h", "4h", "1d"}:
            raise ContractValidationError("dataset interval must be 5m, 15m, 1h, 4h, or 1d")
        if (self.data_start is None) != (self.data_end is None):
            raise ContractValidationError("data_start and data_end must be provided together")
        if self.data_start is not None and self.data_end is not None:
            _require_aware(self.data_start, "data_start")
            _require_aware(self.data_end, "data_end")
            if self.data_start >= self.data_end:
                raise ContractValidationError("data_start must be earlier than data_end")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> DatasetRef:
        data = _object(
            value,
            required={"version", "content_sha256", "symbol", "interval"},
            optional={"data_start", "data_end"},
            name="dataset",
        )
        return cls(
            version=_string(data["version"], "dataset.version"),
            content_sha256=_string(data["content_sha256"], "dataset.content_sha256"),
            symbol=_string(data["symbol"], "dataset.symbol"),
            interval=_string(data["interval"], "dataset.interval"),  # type: ignore[arg-type]
            data_start=_optional_time(data.get("data_start"), "dataset.data_start"),
            data_end=_optional_time(data.get("data_end"), "dataset.data_end"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "version": self.version,
            "content_sha256": self.content_sha256,
            "symbol": self.symbol,
            "interval": self.interval,
        }
        if self.data_start is not None:
            result["data_start"] = _isoformat(self.data_start)
            result["data_end"] = _isoformat(self.data_end)  # type: ignore[arg-type]
        return result


@dataclass(frozen=True, slots=True)
class StrategyRef:
    name: StrategyName
    version: str
    parameters: Mapping[str, ParameterValue]

    def __post_init__(self) -> None:
        if self.name not in {"buy-and-hold", "ema-cross", "donchian-atr"}:
            raise ContractValidationError(f"unsupported strategy: {self.name}")
        if self.version != STRATEGY_VERSION:
            raise ContractValidationError(
                f"strategy version must be {STRATEGY_VERSION} for contract v1"
            )
        parameters = dict(self.parameters)
        _validate_strategy_parameters(self.name, parameters)
        object.__setattr__(self, "parameters", MappingProxyType(parameters))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> StrategyRef:
        data = _object(
            value,
            required={"name", "version", "parameters"},
            optional=set(),
            name="strategy",
        )
        parameters = data["parameters"]
        if not isinstance(parameters, Mapping):
            raise ContractValidationError("strategy.parameters must be an object")
        return cls(
            name=_string(data["name"], "strategy.name"),  # type: ignore[arg-type]
            version=_string(data["version"], "strategy.version"),
            parameters=dict(parameters),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class BacktestConfigContract:
    initial_cash: Decimal = Decimal("100000")
    fee_bps: Decimal = Decimal("10")
    slippage_bps: Decimal = Decimal("5")
    max_target_exposure: Decimal = Decimal("1")
    liquidate_at_end: bool = True

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ContractValidationError("config.initial_cash must be positive")
        if self.fee_bps < 0 or self.fee_bps > 1000:
            raise ContractValidationError("config.fee_bps must be in [0, 1000]")
        if self.slippage_bps < 0 or self.slippage_bps > 1000:
            raise ContractValidationError("config.slippage_bps must be in [0, 1000]")
        if not Decimal("0") < self.max_target_exposure <= Decimal("1"):
            raise ContractValidationError("config.max_target_exposure must be in (0, 1]")
        if not isinstance(self.liquidate_at_end, bool):
            raise ContractValidationError("config.liquidate_at_end must be a boolean")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BacktestConfigContract:
        data = _object(
            value,
            required={
                "initial_cash",
                "fee_bps",
                "slippage_bps",
                "max_target_exposure",
                "liquidate_at_end",
            },
            optional=set(),
            name="config",
        )
        liquidate = data["liquidate_at_end"]
        if not isinstance(liquidate, bool):
            raise ContractValidationError("config.liquidate_at_end must be a boolean")
        return cls(
            initial_cash=_decimal(data["initial_cash"], "config.initial_cash"),
            fee_bps=_decimal(data["fee_bps"], "config.fee_bps"),
            slippage_bps=_decimal(data["slippage_bps"], "config.slippage_bps"),
            max_target_exposure=_decimal(data["max_target_exposure"], "config.max_target_exposure"),
            liquidate_at_end=liquidate,
        )

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "initial_cash": str(self.initial_cash),
            "fee_bps": str(self.fee_bps),
            "slippage_bps": str(self.slippage_bps),
            "max_target_exposure": str(self.max_target_exposure),
            "liquidate_at_end": self.liquidate_at_end,
        }


@dataclass(frozen=True, slots=True)
class BacktestSubmission:
    idempotency_key: str
    dataset: DatasetRef
    strategy: StrategyRef
    config: BacktestConfigContract
    label: str | None = None
    note: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError(f"schema_version must be {SCHEMA_VERSION}")
        if not _IDEMPOTENCY_KEY.fullmatch(self.idempotency_key):
            raise ContractValidationError("idempotency_key has an invalid format")
        _optional_text(self.label, "label", maximum=120)
        _optional_text(self.note, "note", maximum=500)
        if self.strategy.name == "buy-and-hold":
            strategy_exposure = Decimal(self.strategy.parameters["target_exposure"])
        elif self.strategy.name == "donchian-atr":
            strategy_exposure = Decimal(self.strategy.parameters["max_exposure"])
        else:
            strategy_exposure = Decimal("1")
        if strategy_exposure > self.config.max_target_exposure:
            raise ContractValidationError(
                "strategy exposure cannot exceed config.max_target_exposure"
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BacktestSubmission:
        data = _object(
            value,
            required={"schema_version", "idempotency_key", "dataset", "strategy", "config"},
            optional={"label", "note"},
            name="backtest submission",
        )
        return cls(
            schema_version=_string(data["schema_version"], "schema_version"),
            idempotency_key=_string(data["idempotency_key"], "idempotency_key"),
            label=_optional_string(data.get("label"), "label"),
            note=_optional_string(data.get("note"), "note"),
            dataset=DatasetRef.from_dict(_mapping(data["dataset"], "dataset")),
            strategy=StrategyRef.from_dict(_mapping(data["strategy"], "strategy")),
            config=BacktestConfigContract.from_dict(_mapping(data["config"], "config")),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "idempotency_key": self.idempotency_key,
            "dataset": self.dataset.to_dict(),
            "strategy": self.strategy.to_dict(),
            "config": self.config.to_dict(),
        }
        if self.label is not None:
            result["label"] = self.label
        if self.note is not None:
            result["note"] = self.note
        return result


@dataclass(frozen=True, slots=True)
class TaskError:
    code: str
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        if not _ERROR_CODE.fullmatch(self.code):
            raise ContractValidationError("task error code has an invalid format")
        if not self.message or len(self.message) > 500:
            raise ContractValidationError("task error message must contain 1 to 500 characters")
        if not isinstance(self.retryable, bool):
            raise ContractValidationError("task error retryable must be a boolean")

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(frozen=True, slots=True)
class BacktestTask:
    task_id: str
    status: TaskStatus
    created_at: datetime
    request: BacktestSubmission
    started_at: datetime | None = None
    finished_at: datetime | None = None
    run_id: str | None = None
    reused: bool | None = None
    error: TaskError | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError(f"schema_version must be {SCHEMA_VERSION}")
        if not _TASK_ID.fullmatch(self.task_id):
            raise ContractValidationError("task_id must match task_<16 lowercase hex>")
        if self.status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise ContractValidationError(f"unsupported task status: {self.status}")
        _require_aware(self.created_at, "created_at")
        if self.started_at is not None:
            _require_aware(self.started_at, "started_at")
            if self.started_at < self.created_at:
                raise ContractValidationError("started_at cannot be earlier than created_at")
        if self.finished_at is not None:
            _require_aware(self.finished_at, "finished_at")
            if self.finished_at < (self.started_at or self.created_at):
                raise ContractValidationError("finished_at cannot precede task start")
        if self.run_id is not None and not _HEX_16.fullmatch(self.run_id):
            raise ContractValidationError("run_id must be 16 lowercase hex characters")
        self._validate_state()

    def _validate_state(self) -> None:
        if self.status == "queued":
            if any(
                value is not None
                for value in (
                    self.started_at,
                    self.finished_at,
                    self.run_id,
                    self.reused,
                    self.error,
                )
            ):
                raise ContractValidationError("queued task cannot contain result fields")
        elif self.status == "running":
            if self.started_at is None or any(
                value is not None
                for value in (self.finished_at, self.run_id, self.reused, self.error)
            ):
                raise ContractValidationError(
                    "running task requires started_at and no result fields"
                )
        elif self.status == "succeeded":
            if (
                self.started_at is None
                or self.finished_at is None
                or self.run_id is None
                or self.reused is None
                or self.error is not None
            ):
                raise ContractValidationError(
                    "succeeded task requires timestamps, run_id, and reused"
                )
        elif self.status == "failed":
            if (
                self.started_at is None
                or self.finished_at is None
                or self.error is None
                or self.run_id is not None
                or self.reused is not None
            ):
                raise ContractValidationError(
                    "failed task requires timestamps and error without a result"
                )
        elif self.status == "cancelled" and (
            self.finished_at is None or self.run_id is not None or self.reused is not None
        ):
            raise ContractValidationError("cancelled task requires finished_at without a result")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "status": self.status,
            "created_at": _isoformat(self.created_at),
            "started_at": _isoformat(self.started_at) if self.started_at else None,
            "finished_at": _isoformat(self.finished_at) if self.finished_at else None,
            "request": self.request.to_dict(),
            "run_id": self.run_id,
            "reused": self.reused,
            "error": self.error.to_dict() if self.error else None,
        }


@dataclass(frozen=True, slots=True)
class ExperimentMetrics:
    initial_equity: float
    final_equity: float
    total_return: float
    sharpe_ratio: float | None
    max_drawdown: float
    trade_count: int
    fill_count: int
    fees_paid: float

    def __post_init__(self) -> None:
        for name in (
            "initial_equity",
            "final_equity",
            "total_return",
            "max_drawdown",
            "fees_paid",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise ContractValidationError(f"metrics.{name} must be finite")
        if self.sharpe_ratio is not None and not math.isfinite(self.sharpe_ratio):
            raise ContractValidationError("metrics.sharpe_ratio must be finite or null")
        if not 0 <= self.max_drawdown <= 1:
            raise ContractValidationError("metrics.max_drawdown must be in [0, 1]")
        if (
            not isinstance(self.trade_count, int)
            or isinstance(self.trade_count, bool)
            or not isinstance(self.fill_count, int)
            or isinstance(self.fill_count, bool)
            or self.trade_count < 0
            or self.fill_count < 0
        ):
            raise ContractValidationError("metric counts must be non-negative")
        if self.fees_paid < 0:
            raise ContractValidationError("metrics.fees_paid must be non-negative")

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "initial_equity": self.initial_equity,
            "final_equity": self.final_equity,
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "trade_count": self.trade_count,
            "fill_count": self.fill_count,
            "fees_paid": self.fees_paid,
        }


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    run_id: str
    created_at: datetime
    request: BacktestSubmission
    engine_version: str
    metrics_version: str
    metrics: ExperimentMetrics
    artifacts: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError(f"schema_version must be {SCHEMA_VERSION}")
        if not _HEX_16.fullmatch(self.run_id):
            raise ContractValidationError("run_id must be 16 lowercase hex characters")
        _require_aware(self.created_at, "created_at")
        if not _SEMVER.fullmatch(self.engine_version):
            raise ContractValidationError("engine_version must be semantic version")
        if not _SEMVER.fullmatch(self.metrics_version):
            raise ContractValidationError("metrics_version must be semantic version")
        if not self.artifacts or len(set(self.artifacts)) != len(self.artifacts):
            raise ContractValidationError("artifacts must be non-empty and unique")
        if not all(_ARTIFACT_NAME.fullmatch(name) for name in self.artifacts):
            raise ContractValidationError("artifacts must be relative file names")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at": _isoformat(self.created_at),
            "request": self.request.to_dict(),
            "engine_version": self.engine_version,
            "metrics_version": self.metrics_version,
            "metrics": self.metrics.to_dict(),
            "artifacts": list(self.artifacts),
        }


def strategy_catalog() -> dict[str, Any]:
    """Return editable parameter metadata for the three contract-v1 strategies."""
    return {
        "schema_version": SCHEMA_VERSION,
        "strategies": [
            {
                "name": "buy-and-hold",
                "version": STRATEGY_VERSION,
                "label": "Buy & Hold",
                "description": "Passive long-only market exposure benchmark.",
                "category": "benchmark",
                "stage": "benchmark",
                "implementation": "quantos_backtest.strategies.BuyAndHoldStrategy",
                "supported_intervals": ["5m", "15m", "1h", "4h", "1d"],
                "parameters": [
                    _parameter("target_exposure", "decimal", "Target exposure", "1", "0.01", "1")
                ],
            },
            {
                "name": "ema-cross",
                "version": STRATEGY_VERSION,
                "label": "EMA Cross",
                "description": "Long-only trend state from fast and slow exponential averages.",
                "category": "trend",
                "stage": "candidate",
                "implementation": "quantos_backtest.strategies.EmaCrossStrategy",
                "supported_intervals": ["15m", "1h", "4h", "1d"],
                "parameters": [
                    _parameter("fast_period", "integer", "Fast period", 20, 1, 1000),
                    _parameter("slow_period", "integer", "Slow period", 50, 2, 2000),
                ],
            },
            {
                "name": "donchian-atr",
                "version": STRATEGY_VERSION,
                "label": "Donchian ATR",
                "description": "Channel breakout with ATR volatility-targeted exposure.",
                "category": "trend",
                "stage": "candidate",
                "implementation": "quantos_backtest.strategies.DonchianAtrStrategy",
                "supported_intervals": ["1h", "4h", "1d"],
                "parameters": [
                    _parameter("entry_period", "integer", "Entry period", 55, 2, 2000),
                    _parameter("exit_period", "integer", "Exit period", 20, 1, 2000),
                    _parameter("atr_period", "integer", "ATR period", 20, 2, 2000),
                    _parameter(
                        "target_annual_volatility",
                        "decimal",
                        "Target annual volatility",
                        "0.20",
                        "0.01",
                        "2",
                    ),
                    _parameter("max_exposure", "decimal", "Maximum exposure", "1", "0.01", "1"),
                    _parameter(
                        "rebalance_threshold",
                        "decimal",
                        "Rebalance threshold",
                        "0.05",
                        "0",
                        "1",
                    ),
                ],
            },
        ],
    }


def _validate_strategy_parameters(
    name: StrategyName,
    parameters: dict[str, ParameterValue],
) -> None:
    if name == "buy-and-hold":
        _exact_keys(parameters, {"target_exposure"}, "buy-and-hold parameters")
        _bounded_decimal(parameters["target_exposure"], "target_exposure", lower=0, upper=1)
        return
    if name == "ema-cross":
        _exact_keys(parameters, {"fast_period", "slow_period"}, "ema-cross parameters")
        fast = _integer(parameters["fast_period"], "fast_period", minimum=1, maximum=1000)
        slow = _integer(parameters["slow_period"], "slow_period", minimum=2, maximum=2000)
        if fast >= slow:
            raise ContractValidationError("fast_period must be less than slow_period")
        return

    expected = {
        "entry_period",
        "exit_period",
        "atr_period",
        "target_annual_volatility",
        "max_exposure",
        "rebalance_threshold",
    }
    _exact_keys(parameters, expected, "donchian-atr parameters")
    entry = _integer(parameters["entry_period"], "entry_period", minimum=2, maximum=2000)
    exit_period = _integer(parameters["exit_period"], "exit_period", minimum=1, maximum=2000)
    _integer(parameters["atr_period"], "atr_period", minimum=2, maximum=2000)
    if exit_period > entry:
        raise ContractValidationError("exit_period must not exceed entry_period")
    _bounded_decimal(
        parameters["target_annual_volatility"],
        "target_annual_volatility",
        lower=0,
        upper=2,
    )
    _bounded_decimal(parameters["max_exposure"], "max_exposure", lower=0, upper=1)
    _bounded_decimal(
        parameters["rebalance_threshold"],
        "rebalance_threshold",
        lower=0,
        upper=1,
        lower_inclusive=True,
    )


def _parameter(
    key: str,
    kind: Literal["integer", "decimal"],
    label: str,
    default: int | str,
    minimum: int | str,
    maximum: int | str,
) -> dict[str, Any]:
    return {
        "key": key,
        "kind": kind,
        "label": label,
        "default": default,
        "minimum": minimum,
        "maximum": maximum,
    }


def _object(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str],
    name: str,
) -> dict[str, Any]:
    data = dict(value)
    missing = required - data.keys()
    unknown = data.keys() - required - optional
    if missing:
        raise ContractValidationError(f"{name} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ContractValidationError(f"{name} unknown fields: {', '.join(sorted(unknown))}")
    return data


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    missing = expected - value.keys()
    unknown = value.keys() - expected
    if missing:
        raise ContractValidationError(f"{name} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ContractValidationError(f"{name} unknown fields: {', '.join(sorted(unknown))}")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{name} must be an object")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ContractValidationError(f"{name} must be a string")
    return value


def _optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name)


def _optional_text(value: str | None, name: str, *, maximum: int) -> None:
    if value is not None and (not value or len(value) > maximum):
        raise ContractValidationError(f"{name} must contain 1 to {maximum} characters")


def _decimal(value: Any, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ContractValidationError(f"{name} must be an exact decimal string")
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise ContractValidationError(f"{name} must be a finite plain decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ContractValidationError(f"{name} must be a decimal string") from exc
    if not parsed.is_finite():
        raise ContractValidationError(f"{name} must be a finite plain decimal string")
    return parsed


def _bounded_decimal(
    value: Any,
    name: str,
    *,
    lower: int,
    upper: int,
    lower_inclusive: bool = False,
) -> Decimal:
    parsed = _decimal(value, name)
    lower_valid = parsed >= lower if lower_inclusive else parsed > lower
    if not lower_valid or parsed > upper:
        bracket = "[" if lower_inclusive else "("
        raise ContractValidationError(f"{name} must be in {bracket}{lower}, {upper}]")
    return parsed


def _integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ContractValidationError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ContractValidationError(f"{name} must be in [{minimum}, {maximum}]")
    return value


def _optional_time(value: Any, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractValidationError(f"{name} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractValidationError(f"{name} must be an RFC 3339 timestamp") from exc
    _require_aware(parsed, name)
    return parsed.astimezone(UTC)


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractValidationError(f"{name} must include a timezone")


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
