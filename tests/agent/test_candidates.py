from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from quantos_api_contracts import CandidateProposal
from quantos_candidates import CandidateDraftStore, CandidateError, CandidateStore
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


def proposal_with(slug: str, title: str) -> CandidateProposal:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["strategy_slug"] = slug
    payload["title"] = title
    return CandidateProposal.from_dict(payload)


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


def test_candidate_store_allows_only_one_proposal_per_strategy_slug(tmp_path: Path) -> None:
    store = CandidateStore(tmp_path, now=Clock())
    store.propose(proposal())

    with pytest.raises(CandidateError, match="strategy slug"):
        store.propose(proposal_with("volatility-breakout", "Reworded volatility breakout"))


def test_candidate_drafts_are_explainable_unique_and_limited_per_week(tmp_path: Path) -> None:
    candidates = CandidateStore(tmp_path / "candidates", now=Clock())
    first, _ = candidates.propose(proposal())
    second, _ = candidates.propose(
        proposal_with("mean-reversion-envelope", "Volatility envelope mean reversion")
    )
    third, _ = candidates.propose(
        proposal_with("session-momentum", "Session-aware momentum continuation")
    )
    complex_payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    complex_payload["strategy_slug"] = "over-parameterized-trend"
    complex_payload["title"] = "Over-parameterized trend candidate"
    base_parameter = complex_payload["parameters"][0]
    complex_payload["parameters"] = []
    for index in range(7):
        parameter = copy.deepcopy(base_parameter)
        parameter["key"] = f"period_{index}"
        complex_payload["parameters"].append(parameter)
    complex_candidate, _ = candidates.propose(CandidateProposal.from_dict(complex_payload))
    drafts = CandidateDraftStore(tmp_path / "drafts", candidates, now=Clock())

    prepared = drafts.prepare(first.proposal_id)
    assert prepared.iso_week == "2026-W31"
    assert prepared.slot == 1
    package = tmp_path / "drafts" / prepared.iso_week / prepared.draft_id
    assert sorted(path.name for path in package.iterdir()) == [
        "PULL_REQUEST.md",
        "proposal.json",
        "record.json",
        "review-checklist.json",
    ]
    body = (package / "PULL_REQUEST.md").read_text(encoding="utf-8")
    assert "This package contains no strategy code" in body
    assert "Time Series Momentum" in body

    with pytest.raises(CandidateError, match="already has"):
        drafts.prepare(first.proposal_id)
    second_draft = drafts.prepare(second.proposal_id)
    assert second_draft.slot == 2
    with pytest.raises(CandidateError, match="weekly limit"):
        drafts.prepare(third.proposal_id)
    with pytest.raises(CandidateError, match="explainable"):
        drafts.prepare(complex_candidate.proposal_id)
    assert [item.draft_id for item in drafts.list()] == [
        second_draft.draft_id,
        prepared.draft_id,
    ]


def test_candidate_draft_requires_proposed_state_and_rejects_tampering(tmp_path: Path) -> None:
    candidates = CandidateStore(tmp_path / "candidates", now=Clock())
    candidate, _ = candidates.propose(proposal())
    candidates.mark_implemented(
        candidate.proposal_id,
        implementation_ref="quantos_strategy.volatility.VolatilityBreakout",
        test_ids=("tests.strategy.test_volatility_entries",),
        actor_name="implementation-agent",
    )
    drafts = CandidateDraftStore(tmp_path / "drafts", candidates, now=Clock())
    with pytest.raises(CandidateError, match="only a proposed"):
        drafts.prepare(candidate.proposal_id)

    fresh, _ = candidates.propose(proposal_with("range-expansion", "Range expansion continuation"))
    prepared = drafts.prepare(fresh.proposal_id)
    record_path = tmp_path / "drafts" / prepared.iso_week / prepared.draft_id / "record.json"
    raw = json.loads(record_path.read_text(encoding="utf-8"))
    raw["slot"] = 3
    record_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(CandidateError, match="invalid"):
        drafts.list()


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
    proposal_id = output["proposal_id"]

    assert main(["candidate", "list", "--output-root", str(root)]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing[0]["proposal"]["strategy_slug"] == "volatility-breakout"

    draft_root = tmp_path / "drafts"
    assert (
        main(
            [
                "candidate",
                "prepare-draft",
                "--id",
                proposal_id,
                "--candidate-root",
                str(root),
                "--draft-root",
                str(draft_root),
            ]
        )
        == 0
    )
    draft = json.loads(capsys.readouterr().out)
    assert draft["status"] == "prepared"
    assert (
        main(
            [
                "candidate",
                "list-drafts",
                "--candidate-root",
                str(root),
                "--draft-root",
                str(draft_root),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)[0]["draft_id"] == draft["draft_id"]

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
