"""Candidate proposal and guarded lifecycle commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from quantos_api_contracts import CandidateProposal, ContractValidationError

from .errors import CandidateError
from .store import CandidateStore


def register_parser(commands: Any) -> None:
    candidate = commands.add_parser("candidate", help="manage guarded strategy candidates")
    actions = candidate.add_subparsers(dest="command", required=True)

    propose = actions.add_parser("propose", help="validate and persist a bounded Agent proposal")
    propose.add_argument("--input", required=True, type=Path)
    propose.add_argument("--output-root", type=Path, default=Path("var/quantos/candidates"))

    implemented = actions.add_parser("implemented", help="attach implementation and tests")
    implemented.add_argument("--id", required=True)
    implemented.add_argument("--implementation", required=True)
    implemented.add_argument("--test-id", required=True, action="append")
    implemented.add_argument("--actor", required=True)
    implemented.add_argument("--output-root", type=Path, default=Path("var/quantos/candidates"))

    review = actions.add_parser("attach-review", help="validate and attach a passed review")
    review.add_argument("--id", required=True)
    review.add_argument("--review", required=True, type=Path)
    review.add_argument("--output-root", type=Path, default=Path("var/quantos/candidates"))

    decide = actions.add_parser("decide", help="record an explicit human decision")
    decide.add_argument("--id", required=True)
    decide.add_argument("--decision", required=True, choices=("approve", "reject"))
    decide.add_argument("--actor", required=True)
    decide.add_argument("--rationale", required=True)
    decide.add_argument("--output-root", type=Path, default=Path("var/quantos/candidates"))

    listing = actions.add_parser("list", help="list candidate lifecycle records")
    listing.add_argument("--output-root", type=Path, default=Path("var/quantos/candidates"))


def run(args: argparse.Namespace) -> int:
    store = CandidateStore(args.output_root)
    if args.command == "propose":
        try:
            raw = json.loads(args.input.read_text(encoding="utf-8"))
            proposal = CandidateProposal.from_dict(raw)
        except (json.JSONDecodeError, ContractValidationError, TypeError) as exc:
            raise CandidateError(f"candidate proposal is invalid: {exc}") from exc
        record, reused = store.propose(proposal)
        _print(record, reused=reused)
        return 0
    if args.command == "implemented":
        record = store.mark_implemented(
            args.id,
            implementation_ref=args.implementation,
            test_ids=tuple(args.test_id),
            actor_name=args.actor,
        )
        _print(record)
        return 0
    if args.command == "attach-review":
        record = store.attach_robustness(args.id, args.review)
        _print(record)
        return 0
    if args.command == "decide":
        record = store.decide(
            args.id,
            decision=args.decision,
            actor_name=args.actor,
            rationale=args.rationale,
        )
        _print(record)
        return 0
    print(json.dumps([record.to_dict() for record in store.list()], indent=2, sort_keys=True))
    return 0


def _print(record, *, reused: bool = False) -> None:
    print(
        json.dumps(
            {
                "proposal_id": record.proposal_id,
                "status": record.status,
                "updated_at": record.updated_at.isoformat().replace("+00:00", "Z"),
                "reused": reused,
            },
            sort_keys=True,
        )
    )
