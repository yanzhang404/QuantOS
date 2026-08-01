from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from quantos_api_contracts import CandidateProposal, ContractValidationError

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "candidates" / "sample-proposal.v1.json"


def proposal_payload() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_candidate_proposal_round_trips_bounded_fields() -> None:
    payload = proposal_payload()

    proposal = CandidateProposal.from_dict(payload)

    assert proposal.to_dict() == payload
    assert proposal.parameters[1].default == "0.20"


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda value: value.update({"command": "curl example.test"}), "fields are invalid"),
        (
            lambda value: value["implementation_plan"].__setitem__(0, "Run this; then deploy"),
            "prose",
        ),
        (lambda value: value.__setitem__("strategy_slug", "ema-cross"), "already registered"),
        (lambda value: value.__setitem__("title", "<b>Injected title</b>"), "plain text"),
        (
            lambda value: value["sources"][0].__setitem__("url", "http://localhost/paper"),
            "public HTTPS",
        ),
    ],
)
def test_candidate_proposal_rejects_unsafe_or_unbounded_inputs(mutate, match: str) -> None:
    payload = proposal_payload()
    mutate(payload)

    with pytest.raises(ContractValidationError, match=match):
        CandidateProposal.from_dict(payload)


def test_candidate_proposal_requires_unique_parameters_and_valid_decimal_bounds() -> None:
    duplicated = proposal_payload()
    duplicated["parameters"].append(copy.deepcopy(duplicated["parameters"][0]))

    with pytest.raises(ContractValidationError, match="unique"):
        CandidateProposal.from_dict(duplicated)

    invalid_decimal = proposal_payload()
    invalid_decimal["parameters"][1]["default"] = "NaN"

    with pytest.raises(ContractValidationError, match="within bounds"):
        CandidateProposal.from_dict(invalid_decimal)
