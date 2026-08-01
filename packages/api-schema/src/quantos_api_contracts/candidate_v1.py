"""Bounded Agent-authored strategy candidate proposal contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from .backtest_v1 import ContractValidationError

SCHEMA_VERSION = "candidate-proposal.v1"
_SLUG = re.compile(r"^[a-z][a-z0-9-]{2,39}$")
_KEY = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_INTERVALS = frozenset({"5m", "15m", "1h", "4h", "1d"})
_CATEGORIES = frozenset({"trend", "mean_reversion", "intraday"})
_RESERVED = frozenset({"buy-and-hold", "ema-cross", "donchian-atr"})
_COMMAND_MARKERS = ("\n", "`", "$(`", "&&", "||", ";", "<script", "../", "/etc/")


def _exact_keys(raw: Any, expected: set[str], label: str) -> None:
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ContractValidationError(f"{label} fields are invalid")


def _text(value: Any, label: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str) or value != value.strip() or not minimum <= len(value) <= maximum:
        raise ContractValidationError(f"{label} must contain {minimum}-{maximum} characters")
    return value


def _plan_text(value: Any, label: str) -> str:
    text = _text(value, label, 8, 200)
    if any(marker in text.lower() for marker in _COMMAND_MARKERS):
        raise ContractValidationError(f"{label} must be prose, not code or commands")
    return text


@dataclass(frozen=True, slots=True)
class CandidateParameter:
    key: str
    kind: str
    label: str
    default: int | str
    minimum: int | str
    maximum: int | str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CandidateParameter:
        _exact_keys(raw, {"key", "kind", "label", "default", "minimum", "maximum"}, "parameter")
        key = raw["key"]
        kind = raw["kind"]
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ContractValidationError("parameter key is invalid")
        if kind not in {"integer", "decimal"}:
            raise ContractValidationError("parameter kind is invalid")
        label = _text(raw["label"], "parameter label", 2, 80)
        values = (raw["minimum"], raw["default"], raw["maximum"])
        if kind == "integer":
            if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
                raise ContractValidationError("integer parameter bounds must be integers")
            if not values[0] <= values[1] <= values[2]:
                raise ContractValidationError("parameter default must be within bounds")
        else:
            if any(not isinstance(value, str) for value in values):
                raise ContractValidationError("decimal parameter bounds must be strings")
            try:
                decimals = tuple(Decimal(value) for value in values)
            except InvalidOperation as exc:
                raise ContractValidationError("decimal parameter bounds are invalid") from exc
            if (
                not all(value.is_finite() for value in decimals)
                or not decimals[0] <= decimals[1] <= decimals[2]
            ):
                raise ContractValidationError("parameter default must be within bounds")
        return cls(
            key=key, kind=kind, label=label, default=values[1], minimum=values[0], maximum=values[2]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "label": self.label,
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True, slots=True)
class CandidateSource:
    title: str
    url: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CandidateSource:
        _exact_keys(raw, {"title", "url"}, "source")
        title = _text(raw["title"], "source title", 4, 200)
        url = _text(raw["url"], "source URL", 8, 500)
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ContractValidationError("source URL must be public HTTPS without credentials")
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            raise ContractValidationError("source URL must not target localhost")
        return cls(title=title, url=url)

    def to_dict(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url}


@dataclass(frozen=True, slots=True)
class CandidateProposal:
    strategy_slug: str
    title: str
    hypothesis: str
    rationale: str
    category: str
    supported_intervals: tuple[str, ...]
    parameters: tuple[CandidateParameter, ...]
    implementation_plan: tuple[str, ...]
    research_plan: tuple[str, ...]
    sources: tuple[CandidateSource, ...]
    agent_name: str
    workflow_version: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CandidateProposal:
        expected = {
            "schema_version",
            "strategy_slug",
            "title",
            "hypothesis",
            "rationale",
            "category",
            "supported_intervals",
            "parameters",
            "implementation_plan",
            "research_plan",
            "sources",
            "proposed_by",
        }
        _exact_keys(raw, expected, "proposal")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise ContractValidationError(f"schema_version must be {SCHEMA_VERSION}")
        slug = raw["strategy_slug"]
        if not isinstance(slug, str) or not _SLUG.fullmatch(slug) or slug in _RESERVED:
            raise ContractValidationError("strategy_slug is invalid or already registered")
        category = raw["category"]
        if category not in _CATEGORIES:
            raise ContractValidationError("category is invalid")
        intervals = raw["supported_intervals"]
        if (
            not isinstance(intervals, list)
            or not 1 <= len(intervals) <= 5
            or len(set(intervals)) != len(intervals)
            or any(value not in _INTERVALS for value in intervals)
        ):
            raise ContractValidationError("supported_intervals are invalid")
        raw_parameters = raw["parameters"]
        if not isinstance(raw_parameters, list) or not 1 <= len(raw_parameters) <= 12:
            raise ContractValidationError("parameters must contain 1-12 entries")
        parameters = tuple(CandidateParameter.from_dict(value) for value in raw_parameters)
        if len({value.key for value in parameters}) != len(parameters):
            raise ContractValidationError("parameter keys must be unique")
        implementation_plan = _plans(raw["implementation_plan"], "implementation plan")
        research_plan = _plans(raw["research_plan"], "research plan")
        raw_sources = raw["sources"]
        if not isinstance(raw_sources, list) or not 1 <= len(raw_sources) <= 8:
            raise ContractValidationError("sources must contain 1-8 entries")
        sources = tuple(CandidateSource.from_dict(value) for value in raw_sources)
        if len({value.url for value in sources}) != len(sources):
            raise ContractValidationError("source URLs must be unique")
        proposed_by = raw["proposed_by"]
        if not isinstance(proposed_by, dict):
            raise ContractValidationError("proposed_by is invalid")
        _exact_keys(proposed_by, {"kind", "name", "workflow_version"}, "proposed_by")
        if (
            proposed_by["kind"] != "agent"
            or not isinstance(proposed_by["workflow_version"], str)
            or not _VERSION.fullmatch(proposed_by["workflow_version"])
        ):
            raise ContractValidationError("proposed_by is invalid")
        return cls(
            strategy_slug=slug,
            title=_text(raw["title"], "title", 4, 120),
            hypothesis=_text(raw["hypothesis"], "hypothesis", 20, 500),
            rationale=_text(raw["rationale"], "rationale", 20, 1000),
            category=category,
            supported_intervals=tuple(intervals),
            parameters=parameters,
            implementation_plan=implementation_plan,
            research_plan=research_plan,
            sources=sources,
            agent_name=_text(proposed_by["name"], "agent name", 2, 80),
            workflow_version=proposed_by["workflow_version"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "strategy_slug": self.strategy_slug,
            "title": self.title,
            "hypothesis": self.hypothesis,
            "rationale": self.rationale,
            "category": self.category,
            "supported_intervals": list(self.supported_intervals),
            "parameters": [value.to_dict() for value in self.parameters],
            "implementation_plan": list(self.implementation_plan),
            "research_plan": list(self.research_plan),
            "sources": [value.to_dict() for value in self.sources],
            "proposed_by": {
                "kind": "agent",
                "name": self.agent_name,
                "workflow_version": self.workflow_version,
            },
        }


def _plans(raw: Any, label: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 8:
        raise ContractValidationError(f"{label} must contain 1-8 entries")
    return tuple(_plan_text(value, label) for value in raw)
