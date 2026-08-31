"""Rate-limited, local-only candidate draft package preparation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import CandidateError
from .store import CandidateStore

_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_WEEK = re.compile(r"^[0-9]{4}-W(?:0[1-9]|[1-4][0-9]|5[0-3])$")
_SLUG = re.compile(r"^[a-z][a-z0-9-]{2,39}$")
_ARTIFACTS = ("proposal.json", "review-checklist.json", "PULL_REQUEST.md")


@dataclass(frozen=True, slots=True)
class CandidateDraft:
    draft_id: str
    proposal_id: str
    strategy_slug: str
    iso_week: str
    slot: int
    weekly_limit: int
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "candidate-draft.v1",
            "draft_id": self.draft_id,
            "proposal_id": self.proposal_id,
            "strategy_slug": self.strategy_slug,
            "iso_week": self.iso_week,
            "slot": self.slot,
            "weekly_limit": self.weekly_limit,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "status": "prepared",
            "artifacts": list(_ARTIFACTS),
        }


class CandidateDraftStore:
    def __init__(
        self,
        root: Path,
        candidate_store: CandidateStore,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.root = root
        self.candidate_store = candidate_store
        self._now = now

    def prepare(self, proposal_id: str, *, weekly_limit: int = 2) -> CandidateDraft:
        if weekly_limit not in {1, 2}:
            raise CandidateError("weekly_limit must be one or two")
        candidate = self.candidate_store.get(proposal_id)
        if candidate.status != "proposed":
            raise CandidateError("only a proposed candidate can be scheduled")
        if (
            len(candidate.proposal.parameters) > 6
            or len(candidate.proposal.supported_intervals) > 3
        ):
            raise CandidateError("scheduled candidates must remain explainable and narrowly scoped")
        existing = self.list()
        if any(item.proposal_id == proposal_id for item in existing):
            raise CandidateError("candidate proposal already has a prepared draft")
        created_at = self._now().astimezone(UTC)
        iso = created_at.isocalendar()
        iso_week = f"{iso.year:04d}-W{iso.week:02d}"
        weekly = [item for item in existing if item.iso_week == iso_week]
        effective_limit = min((weekly_limit, *(item.weekly_limit for item in weekly)))
        if len(weekly) >= effective_limit:
            raise CandidateError("candidate draft weekly limit has been reached")
        slot = len(weekly) + 1
        draft_id = _draft_id(proposal_id, iso_week)
        draft = CandidateDraft(
            draft_id=draft_id,
            proposal_id=proposal_id,
            strategy_slug=candidate.proposal.strategy_slug,
            iso_week=iso_week,
            slot=slot,
            weekly_limit=effective_limit,
            created_at=created_at,
        )
        self._publish(draft, candidate.proposal.to_dict())
        return draft

    def list(self) -> tuple[CandidateDraft, ...]:
        if not self.root.exists():
            return ()
        drafts: list[CandidateDraft] = []
        for week_path in sorted(self.root.iterdir()):
            if not _is_directory(week_path) or not _WEEK.fullmatch(week_path.name):
                continue
            for draft_path in sorted(week_path.iterdir()):
                if not _is_directory(draft_path) or not _HEX16.fullmatch(draft_path.name):
                    continue
                drafts.append(
                    _read_draft(
                        draft_path / "record.json",
                        expected_week=week_path.name,
                        expected_draft_id=draft_path.name,
                    )
                )
                if len(drafts) > 520:
                    raise CandidateError("candidate draft store exceeds its bounded history")
        identities = {(item.iso_week, item.slot) for item in drafts}
        if (
            len(identities) != len(drafts)
            or len({item.proposal_id for item in drafts}) != len(drafts)
            or any(sum(item.iso_week == week for item in drafts) > 2 for week, _ in identities)
        ):
            raise CandidateError("candidate draft history is inconsistent")
        return tuple(sorted(drafts, key=lambda item: item.created_at, reverse=True))

    def _publish(self, draft: CandidateDraft, proposal: dict[str, Any]) -> None:
        week_root = self.root / draft.iso_week
        destination = week_root / draft.draft_id
        if destination.exists():
            raise CandidateError("candidate draft identity collision")
        week_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".draft-", dir=week_root))
        try:
            _write_json(temporary / "record.json", draft.to_dict())
            _write_json(temporary / "proposal.json", proposal)
            _write_json(temporary / "review-checklist.json", _checklist(draft))
            (temporary / "PULL_REQUEST.md").write_text(
                _pull_request_body(draft, proposal), encoding="utf-8"
            )
            os.replace(temporary, destination)
        except Exception:
            for child in temporary.iterdir() if temporary.exists() else ():
                child.unlink(missing_ok=True)
            temporary.rmdir()
            raise


def _draft_id(proposal_id: str, iso_week: str) -> str:
    payload = json.dumps(
        {
            "schema_version": "candidate-draft.v1",
            "proposal_id": proposal_id,
            "iso_week": iso_week,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _read_draft(path: Path, *, expected_week: str, expected_draft_id: str) -> CandidateDraft:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > 1 << 20:
            raise CandidateError("candidate draft record is invalid")
        raw = json.loads(path.read_text(encoding="utf-8"))
        expected = {
            "schema_version",
            "draft_id",
            "proposal_id",
            "strategy_slug",
            "iso_week",
            "slot",
            "weekly_limit",
            "created_at",
            "status",
            "artifacts",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise CandidateError("candidate draft record is invalid")
        created_at = datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            raise CandidateError("candidate draft record is invalid")
        draft = CandidateDraft(
            draft_id=raw["draft_id"],
            proposal_id=raw["proposal_id"],
            strategy_slug=raw["strategy_slug"],
            iso_week=raw["iso_week"],
            slot=raw["slot"],
            weekly_limit=raw["weekly_limit"],
            created_at=created_at.astimezone(UTC),
        )
        if (
            raw["schema_version"] != "candidate-draft.v1"
            or raw["status"] != "prepared"
            or raw["artifacts"] != list(_ARTIFACTS)
            or not _HEX16.fullmatch(draft.draft_id)
            or not _HEX16.fullmatch(draft.proposal_id)
            or not _SLUG.fullmatch(draft.strategy_slug)
            or not _WEEK.fullmatch(draft.iso_week)
            or draft.slot not in {1, 2}
            or draft.weekly_limit not in {1, 2}
            or draft.slot > draft.weekly_limit
            or _draft_id(draft.proposal_id, draft.iso_week) != draft.draft_id
            or draft.iso_week != expected_week
            or draft.draft_id != expected_draft_id
        ):
            raise CandidateError("candidate draft record is invalid")
        return draft
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CandidateError("candidate draft record is invalid") from exc


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _is_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _checklist(draft: CandidateDraft) -> dict[str, Any]:
    return {
        "schema_version": "candidate-review-checklist.v1",
        "draft_id": draft.draft_id,
        "items": [
            {"key": "hypothesis_falsifiable", "required": True, "complete": False},
            {"key": "implementation_bounded", "required": True, "complete": False},
            {"key": "deterministic_tests", "required": True, "complete": False},
            {"key": "robustness_review", "required": True, "complete": False},
            {"key": "human_decision", "required": True, "complete": False},
        ],
    }


def _pull_request_body(draft: CandidateDraft, proposal: dict[str, Any]) -> str:
    parameters = "\n".join(
        f"- `{item['key']}` ({item['kind']}): {item['minimum']} → "
        f"{item['default']} → {item['maximum']}"
        for item in proposal["parameters"]
    )
    implementation = "\n".join(f"- {item}" for item in proposal["implementation_plan"])
    research = "\n".join(f"- {item}" for item in proposal["research_plan"])
    sources = "\n".join(f"- {item['title']}: {item['url']}" for item in proposal["sources"])
    return f"""# Candidate: {proposal["title"]}

> Draft package `{draft.draft_id}` · {draft.iso_week} slot {draft.slot}/{draft.weekly_limit}

## Hypothesis

{proposal["hypothesis"]}

## Why review it

{proposal["rationale"]}

Supported intervals: {", ".join(proposal["supported_intervals"])}

## Proposed parameters

{parameters}

## Bounded implementation plan

{implementation}

## Research plan

{research}

## Sources

{sources}

## Required gates

- [ ] Repository-owned implementation reference
- [ ] Deterministic unit and boundary tests
- [ ] Strategy-matched four-gate robustness artifact
- [ ] Explicit human approval or rejection

This package contains no strategy code and makes no profitability claim. It does
not open, merge, approve, register, or trade automatically.
"""
