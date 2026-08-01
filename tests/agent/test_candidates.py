from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from quantos_api_contracts import CandidateProposal
from quantos_candidates import CandidateError, CandidateStore
from quantos_cli import main

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "candidates" / "sample-proposal.v1.json"
GATES = ("walk_forward", "neighboring_parameters", "doubled_costs", "multiple_markets")


class Clock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 1, 8, tzinfo=UTC)

    def __call__(self) -> datetime:
        result = self.current
        self.current += timedelta(seconds=1)
        return result


def proposal() -> CandidateProposal:
    return CandidateProposal.from_dict(json.loads(EXAMPLE.read_text(encoding="utf-8")))


def review_payload(*, strategy: str = "volatility-breakout", passed: bool = True) -> dict:
    return {
        "schema_version": "robustness-review.v1",
        "review_id": "0123456789abcdef",
        "status": "completed",
        "passed": passed,
        "strategy": {"name": strategy, "version": "1.0.0", "winner": {}},
        "gates": [
            {
                "name": name,
                "passed": passed,
                "reason": "Deterministic fixture evidence.",
                "observations": {},
                "run_ids": [],
            }
            for name in GATES
        ],
    }


def write_review(path: Path, **overrides) -> Path:
    payload = review_payload(**overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_candidate_lifecycle_requires_matching_evidence_and_human_approval(tmp_path: Path) -> None:
    store = CandidateStore(tmp_path / "candidates", now=Clock())
    record, reused = store.propose(proposal())
    same, reused_again = store.propose(proposal())

    assert reused is False
    assert reused_again is True
    assert same.proposal_id == record.proposal_id
    assert store.list() == (record,)

    with pytest.raises(CandidateError, match="approval requires"):
        store.decide(
            record.proposal_id,
            decision="approve",
            actor_name="Yan Zhang",
            rationale="Approve only after deterministic evidence exists.",
        )

    implemented = store.mark_implemented(
        record.proposal_id,
        implementation_ref="quantos_strategy.volatility.VolatilityBreakout",
        test_ids=("tests.strategy.test_volatility_entries",),
        actor_name="implementation-agent",
    )
    assert implemented.status == "implemented"

    with pytest.raises(CandidateError, match="passed every gate"):
        store.attach_robustness(
            record.proposal_id,
            write_review(tmp_path / "failed.json", passed=False),
        )
    with pytest.raises(CandidateError, match="passed every gate"):
        store.attach_robustness(
            record.proposal_id,
            write_review(tmp_path / "mismatch.json", strategy="another-strategy"),
        )

    review_path = write_review(tmp_path / "passed.json")
    ready = store.attach_robustness(record.proposal_id, review_path)
    assert ready.status == "review_ready"
    assert ready.robustness_review_id == "0123456789abcdef"
    assert len(ready.robustness_sha256 or "") == 64

    approved = store.decide(
        record.proposal_id,
        decision="approve",
        actor_name="Yan Zhang",
        rationale="The evidence is reproducible and suitable for library review.",
    )
    assert approved.status == "approved"
    assert approved.transitions[-1].actor_kind == "human"
    assert store.get(record.proposal_id) == approved

    with pytest.raises(CandidateError, match="terminal"):
        store.decide(
            record.proposal_id,
            decision="reject",
            actor_name="Yan Zhang",
            rationale="A terminal candidate cannot receive another human decision.",
        )


def test_candidate_can_be_rejected_before_implementation(tmp_path: Path) -> None:
    store = CandidateStore(tmp_path, now=Clock())
    proposed, _ = store.propose(proposal())

    rejected = store.decide(
        proposed.proposal_id,
        decision="reject",
        actor_name="Research Owner",
        rationale="The hypothesis overlaps an existing strategy and should not proceed.",
    )

    assert rejected.status == "rejected"
    assert rejected.implementation is None


def test_candidate_store_rejects_tampered_transition_history(tmp_path: Path) -> None:
    store = CandidateStore(tmp_path, now=Clock())
    record, _ = store.propose(proposal())
    path = tmp_path / f"{record.proposal_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["transitions"][0]["actor_kind"] = "system"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(CandidateError, match="inconsistent"):
        store.get(record.proposal_id)


def test_candidate_cli_proposes_lists_and_reports_invalid_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "records"

    assert (
        main(
            [
                "candidate",
                "propose",
                "--input",
                str(EXAMPLE),
                "--output-root",
                str(root),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "proposed"
    assert output["reused"] is False

    assert main(["candidate", "list", "--output-root", str(root)]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing[0]["proposal"]["strategy_slug"] == "volatility-breakout"

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    assert (
        main(
            [
                "candidate",
                "propose",
                "--input",
                str(invalid),
                "--output-root",
                str(root),
            ]
        )
        == 2
    )
    assert "candidate proposal is invalid" in capsys.readouterr().err
