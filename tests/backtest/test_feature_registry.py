from __future__ import annotations

import json
from pathlib import Path

import pytest
from quantos_backtest.features import feature_registry, resolve_feature_lineage

ROOT = Path(__file__).resolve().parents[2]


def test_registry_hashes_are_deterministic_and_bounded() -> None:
    first = feature_registry()
    second = feature_registry()

    assert first == second
    assert first["schema_version"] == "feature-registry.v1"
    assert len(first["features"]) == 5
    assert all(len(item["definition_sha256"]) == 64 for item in first["features"])


def test_resolves_donchian_causality_and_exact_strategy_parameters() -> None:
    lineage = resolve_feature_lineage(
        "donchian-atr",
        {"entry_period": 55, "exit_period": 20, "atr_period": 14},
    )

    by_instance = {item["instance"]: item for item in lineage}
    assert by_instance["entry_channel"]["warmup_bars"] == 55
    assert by_instance["entry_channel"]["strategy_parameter"] == "entry_period"
    assert by_instance["entry_channel"]["uses_current_closed_bar"] is False
    assert by_instance["atr"]["warmup_bars"] == 14
    assert by_instance["atr"]["uses_current_closed_bar"] is True


def test_unknown_strategy_has_no_claimed_lineage_and_invalid_binding_fails() -> None:
    assert resolve_feature_lineage("scripted-test-strategy", {}) == ()
    with pytest.raises(ValueError, match="fast_period"):
        resolve_feature_lineage("ema-cross", {"fast_period": 0, "slow_period": 50})


def test_web_feature_registry_read_model_matches_authoritative_contract() -> None:
    path = ROOT / "apps" / "web" / "app" / "feature-registry.v1.json"
    assert json.loads(path.read_text(encoding="utf-8")) == feature_registry()
