"""Versioned built-in feature registry and strategy lineage resolution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

FEATURE_REGISTRY_VERSION = "feature-registry.v1"


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    feature_id: str
    version: str
    implementation: str
    inputs: tuple[str, ...]
    warmup_parameter: str | None
    uses_current_closed_bar: bool
    description: str

    @property
    def definition_sha256(self) -> str:
        payload = json.dumps(
            self.to_dict(include_hash=False), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        result = {
            "feature_id": self.feature_id,
            "version": self.version,
            "implementation": self.implementation,
            "inputs": list(self.inputs),
            "warmup_parameter": self.warmup_parameter,
            "uses_current_closed_bar": self.uses_current_closed_bar,
            "description": self.description,
        }
        if include_hash:
            result["definition_sha256"] = self.definition_sha256
        return result


DEFINITIONS = {
    "ema": FeatureDefinition(
        "ema",
        "1.0.0",
        "quantos_backtest.strategies.EmaCrossStrategy._update",
        ("close",),
        "period",
        True,
        "Exponentially weighted mean of current and prior closed-bar prices.",
    ),
    "prior-high-channel": FeatureDefinition(
        "prior-high-channel",
        "1.0.0",
        "quantos_backtest.strategies.DonchianAtrStrategy.on_bar",
        ("high",),
        "period",
        False,
        "Maximum high over prior closed bars, excluding the current bar.",
    ),
    "prior-low-channel": FeatureDefinition(
        "prior-low-channel",
        "1.0.0",
        "quantos_backtest.strategies.DonchianAtrStrategy.on_bar",
        ("low",),
        "period",
        False,
        "Minimum low over prior closed bars, excluding the current bar.",
    ),
    "atr": FeatureDefinition(
        "atr",
        "1.0.0",
        "quantos_backtest.strategies.DonchianAtrStrategy._true_range",
        ("high", "low", "close"),
        "period",
        True,
        "Simple moving average of true range through the current closed bar.",
    ),
    "aligned-funding-rate": FeatureDefinition(
        "aligned-funding-rate",
        "1.0.0",
        "quantos_backtest.engine._validate_feature_inputs",
        ("funding_rate", "observation_time", "age_ms", "availability"),
        None,
        True,
        "Latest non-stale funding observation available at the current closed-bar decision time.",
    ),
}

_BINDINGS = {
    "ema-cross": (
        ("ema", "fast_ema", "fast_period"),
        ("ema", "slow_ema", "slow_period"),
    ),
    "donchian-atr": (
        ("prior-high-channel", "entry_channel", "entry_period"),
        ("prior-low-channel", "exit_channel", "exit_period"),
        ("atr", "atr", "atr_period"),
    ),
    "funding-filtered-ema": (
        ("ema", "fast_ema", "fast_period"),
        ("ema", "slow_ema", "slow_period"),
    ),
}

_EXTERNAL_REQUIREMENTS = {
    "funding-filtered-ema": (
        {
            "feature_id": "aligned-funding-rate",
            "series": "funding-rate",
            "required": True,
            "missing_policy": "flat",
        },
    )
}


def feature_registry() -> dict[str, Any]:
    return {
        "schema_version": FEATURE_REGISTRY_VERSION,
        "features": [DEFINITIONS[key].to_dict() for key in sorted(DEFINITIONS)],
        "strategy_bindings": {
            strategy: [
                {
                    "feature_id": feature_id,
                    "instance": instance,
                    "strategy_parameter": parameter,
                }
                for feature_id, instance, parameter in bindings
            ]
            for strategy, bindings in sorted(_BINDINGS.items())
        },
        "strategy_external_requirements": {
            strategy: list(requirements)
            for strategy, requirements in sorted(_EXTERNAL_REQUIREMENTS.items())
        },
    }


def resolve_feature_lineage(
    strategy_name: str, strategy_parameters: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    instances = []
    for feature_id, instance, parameter_name in _BINDINGS.get(strategy_name, ()):
        value = strategy_parameters.get(parameter_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"feature binding requires positive integer {parameter_name}")
        definition = DEFINITIONS[feature_id]
        instances.append(
            {
                "feature_id": feature_id,
                "instance": instance,
                "version": definition.version,
                "definition_sha256": definition.definition_sha256,
                "implementation": definition.implementation,
                "inputs": list(definition.inputs),
                "parameters": {definition.warmup_parameter: value},
                "strategy_parameter": parameter_name,
                "warmup_bars": value,
                "uses_current_closed_bar": definition.uses_current_closed_bar,
            }
        )
    return tuple(instances)
