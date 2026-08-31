"""Atomic single-process store for guarded candidate lifecycle records."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quantos_api_contracts import CandidateProposal, ContractValidationError

from .errors import CandidateError
from .models import CandidateRecord, CandidateTransition, ImplementationEvidence

_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_IMPLEMENTATION = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{7,159}$")
_TEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{3,159}$")
_ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{1,79}$")
_TERMINAL = frozenset({"approved", "rejected"})
_STATUSES = frozenset({"proposed", "implemented", "review_ready", *_TERMINAL})
_GATE_NAMES = frozenset(
    {"walk_forward", "neighboring_parameters", "doubled_costs", "multiple_markets"}
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ROBUSTNESS_SCHEMAS = frozenset({"robustness-review.v1", "robustness-review.v2"})


class CandidateStore:
    def __init__(
        self,
        root: Path,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.root = root
        self._now = now

    def propose(self, proposal: CandidateProposal) -> tuple[CandidateRecord, bool]:
        proposal_id = _proposal_id(proposal)
        path = self._path(proposal_id)
        if path.exists():
            record = self.get(proposal_id)
            if record.proposal != proposal:
                raise CandidateError("candidate proposal identity collision")
            return record, True
        if any(item.proposal.strategy_slug == proposal.strategy_slug for item in self.list()):
            raise CandidateError("strategy slug already has a candidate proposal")
        created_at = self._now()
        record = CandidateRecord(
            proposal_id=proposal_id,
            created_at=created_at,
            updated_at=created_at,
            status="proposed",
            proposal=proposal,
            implementation=None,
            robustness_review_id=None,
            robustness_sha256=None,
            transitions=(
                CandidateTransition(
                    from_status=None,
                    to_status="proposed",
                    actor_kind="agent",
                    actor_name=proposal.agent_name,
                    rationale=(
                        "Bounded candidate proposal accepted for human-visible research review."
                    ),
                    occurred_at=created_at,
                ),
            ),
        )
        self._write(record)
        return record, False

    def mark_implemented(
        self,
        proposal_id: str,
        *,
        implementation_ref: str,
        test_ids: tuple[str, ...],
        actor_name: str,
    ) -> CandidateRecord:
        record = self.get(proposal_id)
        if record.status != "proposed":
            raise CandidateError("only a proposed candidate can be marked implemented")
        if not _IMPLEMENTATION.fullmatch(implementation_ref):
            raise CandidateError("implementation_ref must be a repository-owned Python symbol")
        if (
            not 1 <= len(test_ids) <= 20
            or len(set(test_ids)) != len(test_ids)
            or any(not _TEST_ID.fullmatch(value) for value in test_ids)
        ):
            raise CandidateError("test_ids must contain 1-20 unique deterministic test identifiers")
        actor = _actor(actor_name)
        now = self._now()
        updated = replace(
            record,
            updated_at=now,
            status="implemented",
            implementation=ImplementationEvidence(implementation_ref, test_ids),
            transitions=(
                *record.transitions,
                CandidateTransition(
                    from_status="proposed",
                    to_status="implemented",
                    actor_kind="agent",
                    actor_name=actor,
                    rationale=(
                        "Repository implementation and deterministic test identifiers attached."
                    ),
                    occurred_at=now,
                    evidence_id=implementation_ref,
                ),
            ),
        )
        self._write(updated)
        return updated

    def attach_robustness(self, proposal_id: str, review_path: Path) -> CandidateRecord:
        record = self.get(proposal_id)
        if record.status != "implemented":
            raise CandidateError("only an implemented candidate can enter robustness review")
        raw_bytes = review_path.read_bytes()
        if len(raw_bytes) > 4 << 20:
            raise CandidateError("robustness review is too large")
        try:
            review = json.loads(raw_bytes)
            review_id = review["review_id"]
            gates = review["gates"]
            if not isinstance(gates, list) or any(not isinstance(gate, dict) for gate in gates):
                raise CandidateError("robustness review is invalid")
            gate_names = {gate["name"] for gate in gates}
            if (
                review["schema_version"] not in _ROBUSTNESS_SCHEMAS
                or review["status"] != "completed"
                or review["passed"] is not True
                or review["strategy"]["name"] != record.proposal.strategy_slug
                or not isinstance(review_id, str)
                or not _HEX16.fullmatch(review_id)
                or len(gates) != 4
                or gate_names != _GATE_NAMES
                or not all(gate.get("passed") is True for gate in gates)
            ):
                raise CandidateError("robustness review has not passed every gate")
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise CandidateError("robustness review is invalid") from exc
        digest = hashlib.sha256(raw_bytes).hexdigest()
        now = self._now()
        updated = replace(
            record,
            updated_at=now,
            status="review_ready",
            robustness_review_id=review_id,
            robustness_sha256=digest,
            transitions=(
                *record.transitions,
                CandidateTransition(
                    from_status="implemented",
                    to_status="review_ready",
                    actor_kind="system",
                    actor_name="quantos-robustness-gate",
                    rationale="Validated robustness artifact passes every deterministic gate.",
                    occurred_at=now,
                    evidence_id=review_id,
                ),
            ),
        )
        self._write(updated)
        return updated

    def decide(
        self,
        proposal_id: str,
        *,
        decision: str,
        actor_name: str,
        rationale: str,
    ) -> CandidateRecord:
        record = self.get(proposal_id)
        if record.status in _TERMINAL:
            raise CandidateError("candidate already has a terminal human decision")
        if decision == "approve" and record.status != "review_ready":
            raise CandidateError("approval requires a passed robustness review")
        if decision not in {"approve", "reject"}:
            raise CandidateError("decision must be approve or reject")
        actor = _actor(actor_name)
        rationale = rationale.strip()
        if len(rationale) < 20 or len(rationale) > 500:
            raise CandidateError("human decision rationale must contain 20-500 characters")
        next_status = "approved" if decision == "approve" else "rejected"
        now = self._now()
        updated = replace(
            record,
            updated_at=now,
            status=next_status,
            transitions=(
                *record.transitions,
                CandidateTransition(
                    from_status=record.status,
                    to_status=next_status,
                    actor_kind="human",
                    actor_name=actor,
                    rationale=rationale,
                    occurred_at=now,
                    evidence_id=record.robustness_review_id,
                ),
            ),
        )
        self._write(updated)
        return updated

    def get(self, proposal_id: str) -> CandidateRecord:
        if not _HEX16.fullmatch(proposal_id):
            raise CandidateError("candidate proposal not found")
        path = self._path(proposal_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return _record_from_dict(raw)
        except FileNotFoundError as exc:
            raise CandidateError("candidate proposal not found") from exc
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            ContractValidationError,
        ) as exc:
            raise CandidateError("candidate record is invalid") from exc

    def list(self) -> tuple[CandidateRecord, ...]:
        if not self.root.exists():
            return ()
        records = [
            self.get(path.stem) for path in self.root.glob("*.json") if _HEX16.fullmatch(path.stem)
        ]
        return tuple(sorted(records, key=lambda item: item.created_at, reverse=True))

    def _path(self, proposal_id: str) -> Path:
        return self.root / f"{proposal_id}.json"

    def _write(self, record: CandidateRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".candidate-", suffix=".json", dir=self.root
        )
        temporary_path = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._path(record.proposal_id))
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise


def _proposal_id(proposal: CandidateProposal) -> str:
    encoded = json.dumps(proposal.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _actor(value: Any) -> str:
    if not isinstance(value, str):
        raise CandidateError("actor name is invalid")
    value = value.strip()
    if not _ACTOR.fullmatch(value):
        raise CandidateError("actor name is invalid")
    return value


def _record_from_dict(raw: dict[str, Any]) -> CandidateRecord:
    if raw["schema_version"] != "candidate-record.v1" or set(raw) != {
        "schema_version",
        "proposal_id",
        "created_at",
        "updated_at",
        "status",
        "proposal",
        "implementation",
        "robustness_review_id",
        "robustness_sha256",
        "transitions",
    }:
        raise CandidateError("candidate record fields are invalid")
    proposal = CandidateProposal.from_dict(raw["proposal"])
    if _proposal_id(proposal) != raw["proposal_id"]:
        raise CandidateError("candidate proposal identity mismatch")
    implementation = raw["implementation"]
    parsed_implementation = None
    if implementation is not None:
        if (
            not isinstance(implementation, dict)
            or set(implementation) != {"implementation_ref", "test_ids"}
            or not isinstance(implementation["implementation_ref"], str)
            or not _IMPLEMENTATION.fullmatch(implementation["implementation_ref"])
            or not isinstance(implementation["test_ids"], list)
            or not 1 <= len(implementation["test_ids"]) <= 20
            or len(set(implementation["test_ids"])) != len(implementation["test_ids"])
            or any(
                not isinstance(value, str) or not _TEST_ID.fullmatch(value)
                for value in implementation["test_ids"]
            )
        ):
            raise CandidateError("candidate implementation evidence is invalid")
        parsed_implementation = ImplementationEvidence(
            implementation_ref=implementation["implementation_ref"],
            test_ids=tuple(implementation["test_ids"]),
        )
    transitions = _transitions(raw["transitions"])
    record = CandidateRecord(
        proposal_id=raw["proposal_id"],
        created_at=_time(raw["created_at"]),
        updated_at=_time(raw["updated_at"]),
        status=raw["status"],
        proposal=proposal,
        implementation=parsed_implementation,
        robustness_review_id=raw["robustness_review_id"],
        robustness_sha256=raw["robustness_sha256"],
        transitions=transitions,
    )
    if (
        record.status not in _STATUSES
        or not transitions
        or transitions[-1].to_status != record.status
        or record.updated_at != transitions[-1].occurred_at
        or record.created_at != transitions[0].occurred_at
    ):
        raise CandidateError("candidate transition history is inconsistent")
    _validate_evidence(record)
    return record


def _transitions(raw: Any) -> tuple[CandidateTransition, ...]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 5:
        raise CandidateError("candidate transition history is invalid")
    parsed: list[CandidateTransition] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or set(item) != {
            "from_status",
            "to_status",
            "actor_kind",
            "actor_name",
            "rationale",
            "occurred_at",
            "evidence_id",
        }:
            raise CandidateError("candidate transition history is invalid")
        transition = CandidateTransition(
            from_status=item["from_status"],
            to_status=item["to_status"],
            actor_kind=item["actor_kind"],
            actor_name=_actor(item["actor_name"]),
            rationale=item["rationale"],
            occurred_at=_time(item["occurred_at"]),
            evidence_id=item["evidence_id"],
        )
        previous = parsed[-1].to_status if parsed else None
        permitted = {
            None: {"proposed"},
            "proposed": {"implemented", "rejected"},
            "implemented": {"review_ready", "rejected"},
            "review_ready": {"approved", "rejected"},
        }
        actor_for_status = {
            "proposed": "agent",
            "implemented": "agent",
            "review_ready": "system",
            "approved": "human",
            "rejected": "human",
        }
        if (
            transition.from_status != previous
            or transition.to_status not in _STATUSES
            or transition.to_status not in permitted.get(previous, set())
            or transition.actor_kind not in {"agent", "system", "human"}
            or transition.actor_kind != actor_for_status[transition.to_status]
            or not isinstance(transition.rationale, str)
            or not 8 <= len(transition.rationale) <= 500
            or (parsed and transition.occurred_at < parsed[-1].occurred_at)
            or (index == 0 and transition.to_status != "proposed")
        ):
            raise CandidateError("candidate transition history is inconsistent")
        parsed.append(transition)
    return tuple(parsed)


def _validate_evidence(record: CandidateRecord) -> None:
    visited = {transition.to_status for transition in record.transitions}
    implementation_required = "implemented" in visited
    review_required = "review_ready" in visited
    if (record.implementation is not None) != implementation_required:
        raise CandidateError("candidate implementation state is inconsistent")
    if review_required:
        if (
            not isinstance(record.robustness_review_id, str)
            or not _HEX16.fullmatch(record.robustness_review_id)
            or not isinstance(record.robustness_sha256, str)
            or not _SHA256.fullmatch(record.robustness_sha256)
        ):
            raise CandidateError("candidate robustness evidence is invalid")
    elif record.robustness_review_id is not None or record.robustness_sha256 is not None:
        raise CandidateError("candidate robustness state is inconsistent")


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("candidate timestamp requires timezone")
    return parsed.astimezone(UTC)
