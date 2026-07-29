from __future__ import annotations

import json
from pathlib import Path

ARTIFACT = (
    Path(__file__).parents[2]
    / "examples"
    / "backtest"
    / "donchian-atr-study"
    / "visualization.json"
)


def test_strategy_visualization_artifact_preserves_provenance_and_alignment() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    assert artifact["schema_version"] == "1.0"
    assert artifact["generated_from"] == "results.json"
    assert artifact["window_bars"] == 240
    assert set(artifact["datasets"]) == {
        "btc_development",
        "btc_evaluation",
        "eth_development",
        "eth_evaluation",
    }

    for dataset in artifact["datasets"].values():
        assert len(dataset["dataset_version"]) == 16
        assert len(dataset["content_sha256"]) == 64
        assert len(dataset["bars"]) == 240
        assert list(dataset["runs"]) == [
            "buy-and-hold",
            "ema-cross",
            "donchian-atr",
        ]

        for run in dataset["runs"].values():
            assert len(run["run_id"]) == 16
            assert len(run["equity"]) == len(dataset["bars"])
            assert [point["time"] for point in run["equity"]] == sorted(
                point["time"] for point in run["equity"]
            )
            assert all(-1 <= point["drawdown"] <= 0 for point in run["equity"])
            assert all(fill["side"] in {"buy", "sell"} for fill in run["fills"])
