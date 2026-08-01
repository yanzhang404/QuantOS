"""Durable candidate lifecycle records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from quantos_api_contracts import CandidateProposal


@dataclass(frozen=True, slots=True)
class CandidateTransition:
    from_status: str | None
    to_status: str
    actor_kind: str
    actor_name: str
    rationale: str
    occurred_at: datetime
    evidence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_status": self.from_status,
            "to_status": self.to_status,
            "actor_kind": self.actor_kind,
            "actor_name": self.actor_name,
            "rationale": self.rationale,
            "occurred_at": self.occurred_at.isoformat().replace("+00:00", "Z"),
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True, slots=True)
class ImplementationEvidence:
    implementation_ref: str
    test_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "implementation_ref": self.implementation_ref,
            "test_ids": list(self.test_ids),
        }


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    proposal_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    proposal: CandidateProposal
    implementation: ImplementationEvidence | None
    robustness_review_id: str | None
    robustness_sha256: str | None
    transitions: tuple[CandidateTransition, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "candidate-record.v1",
            "proposal_id": self.proposal_id,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
            "status": self.status,
            "proposal": self.proposal.to_dict(),
            "implementation": self.implementation.to_dict() if self.implementation else None,
            "robustness_review_id": self.robustness_review_id,
            "robustness_sha256": self.robustness_sha256,
            "transitions": [item.to_dict() for item in self.transitions],
        }
