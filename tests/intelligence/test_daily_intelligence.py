from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from quantos_intelligence.errors import IntelligenceValidationError
from quantos_intelligence.models import DailyIntelligenceInput
from quantos_intelligence.scoring import build_snapshot
from quantos_intelligence.store import publish_snapshot

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "examples" / "intelligence" / "sample-input.v1.json"
SAMPLE_SNAPSHOT = ROOT / "examples" / "intelligence" / "sample-snapshot.v1.json"


def sample_payload() -> dict[str, object]:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_builds_reproducible_weighted_snapshot() -> None:
    daily = DailyIntelligenceInput.from_dict(sample_payload())

    first = build_snapshot(daily)
    second = build_snapshot(daily)

    assert first == second
    assert first == json.loads(SAMPLE_SNAPSHOT.read_text(encoding="utf-8"))
    assert first["methodology_version"] == "quantos-sentiment-v1.0.0"
    assert first["status"] == "sample"
    assert first["market_score"] == 27.25
    assert first["news_score"] == 45.43
    assert first["score"] == 31.8
    assert first["label"] == "fear"
    assert first["change"] == -4.7
    assert len(first["factors"]) == 7
    assert len(first["provenance"]["input_sha256"]) == 64
    assert first["brief"]["title_zh"].endswith("恐惧")


def test_publishes_daily_and_latest_atomically(tmp_path: Path) -> None:
    snapshot = build_snapshot(DailyIntelligenceInput.from_dict(sample_payload()))

    daily, latest = publish_snapshot(snapshot, tmp_path)

    assert daily.name == "2026-08-01.json"
    assert json.loads(daily.read_text(encoding="utf-8")) == snapshot
    assert latest.read_bytes() == daily.read_bytes()


def test_rejects_missing_duplicate_or_unsafe_inputs() -> None:
    missing = sample_payload()
    missing["factors"] = missing["factors"][:-1]  # type: ignore[index]
    with pytest.raises(IntelligenceValidationError, match="every methodology factor"):
        DailyIntelligenceInput.from_dict(missing)

    duplicate = sample_payload()
    duplicate["news"][1]["id"] = duplicate["news"][0]["id"]  # type: ignore[index]
    with pytest.raises(IntelligenceValidationError, match="news ids must be unique"):
        DailyIntelligenceInput.from_dict(duplicate)

    unsafe = deepcopy(sample_payload())
    unsafe["news"][0]["url"] = "http://example.com/story"  # type: ignore[index]
    with pytest.raises(IntelligenceValidationError, match="HTTPS URL"):
        DailyIntelligenceInput.from_dict(unsafe)


def test_rejects_unknown_agent_fields() -> None:
    payload = sample_payload()
    payload["command"] = "place-order"

    with pytest.raises(IntelligenceValidationError, match="unknown fields"):
        DailyIntelligenceInput.from_dict(payload)
