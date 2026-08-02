"""Deterministic daily market intelligence for QuantOS."""

from .collector import ObservationHistory, PublicIntelligenceCollector, build_public_client
from .models import DailyIntelligenceInput, FactorObservation, NewsItem
from .scoring import build_snapshot
from .store import publish_snapshot

__all__ = [
    "DailyIntelligenceInput",
    "FactorObservation",
    "NewsItem",
    "ObservationHistory",
    "PublicIntelligenceCollector",
    "build_public_client",
    "build_snapshot",
    "publish_snapshot",
]

__version__ = "0.1.0"
