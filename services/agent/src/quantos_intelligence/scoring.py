"""Versioned, deterministic sentiment scoring and brief assembly."""

# ruff: noqa: RUF001 -- Chinese prose intentionally uses full-width punctuation.

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .models import DailyIntelligenceInput, FactorObservation, NewsItem

METHODOLOGY_VERSION = "quantos-sentiment-v1.0.0"
GENERATOR_VERSION = "0.1.0"
MARKET_WEIGHT = 0.75
NEWS_WEIGHT = 0.25


@dataclass(frozen=True, slots=True)
class FactorMethod:
    weight: float
    direction: str


METHODS: dict[str, FactorMethod] = {
    "crypto_volatility": FactorMethod(0.20, "fear_when_high"),
    "options_positioning": FactorMethod(0.20, "fear_when_high"),
    "perpetual_positioning": FactorMethod(0.20, "greed_when_high"),
    "momentum_volume": FactorMethod(0.15, "greed_when_high"),
    "liquidation_balance": FactorMethod(0.10, "greed_when_high"),
    "market_breadth": FactorMethod(0.10, "greed_when_high"),
    "macro_risk": FactorMethod(0.05, "fear_when_high"),
}

LABELS_EN = {
    "extreme_fear": "Extreme fear",
    "fear": "Fear",
    "neutral": "Neutral",
    "greed": "Greed",
    "extreme_greed": "Extreme greed",
}
LABELS_ZH = {
    "extreme_fear": "极度恐惧",
    "fear": "恐惧",
    "neutral": "中性",
    "greed": "贪婪",
    "extreme_greed": "极度贪婪",
}
FACTOR_NAMES_ZH = {
    "crypto_volatility": "加密资产波动率",
    "options_positioning": "期权仓位",
    "perpetual_positioning": "永续合约仓位",
    "momentum_volume": "动量与成交量",
    "liquidation_balance": "多空清算结构",
    "market_breadth": "市场广度",
    "macro_risk": "宏观风险",
}


def build_snapshot(daily: DailyIntelligenceInput) -> dict[str, Any]:
    factors = [_score_factor(factor) for factor in daily.factors]
    factors.sort(key=lambda factor: (-factor["weight"], factor["key"]))
    market_score = _round(sum(item["contribution"] for item in factors))
    news_score = _score_news(daily.news)
    score = _round(market_score * MARKET_WEIGHT + news_score * NEWS_WEIGHT)
    label = _label(score)
    previous = daily.previous_score
    change = None if previous is None else _round(score - previous)
    ranked_news = sorted(daily.news, key=_news_impact, reverse=True)[:10]
    highlights = [item.summary for item in ranked_news[:3]]
    highlights_zh = [item.summary_zh or item.title_zh or item.summary for item in ranked_news[:3]]
    pressure = sorted(factors, key=lambda item: (item["score"], -item["weight"]))[:2]
    pressure_names = ", ".join(item["key"].replace("_", " ") for item in pressure)
    pressure_names_zh = "、".join(FACTOR_NAMES_ZH[item["key"]] for item in pressure)
    input_payload = daily.to_dict()
    input_sha256 = hashlib.sha256(_canonical_json(input_payload)).hexdigest()
    return {
        "schema_version": "1.0",
        "methodology_version": METHODOLOGY_VERSION,
        "date": daily.date.isoformat(),
        "as_of": input_payload["as_of"],
        "status": daily.status,
        "score": score,
        "previous_score": previous,
        "change": change,
        "label": label,
        "market_score": market_score,
        "news_score": news_score,
        "factors": factors,
        "brief": {
            "title": f"QuantOS daily market brief — {LABELS_EN[label]}",
            "title_zh": f"QuantOS 每日市场简报｜{LABELS_ZH[label]}",
            "summary": (
                f"Composite sentiment is {score:.1f}/100. Market data scored "
                f"{market_score:.1f}; source-weighted news scored {news_score:.1f}. "
                f"The largest defensive pressures are {pressure_names}."
            ),
            "summary_zh": (
                f"综合情绪为 {score:.1f}/100；市场数据得分 {market_score:.1f}，"
                f"来源加权新闻得分 {news_score:.1f}。主要压力来自"
                f"{pressure_names_zh}。"
            ),
            "highlights": highlights,
            "highlights_zh": highlights_zh,
            "news": [item.to_dict() for item in ranked_news],
        },
        "provenance": {
            "input_sha256": input_sha256,
            "generator_version": GENERATOR_VERSION,
            "factor_count": len(factors),
            "news_count": len(daily.news),
        },
    }


def _score_factor(factor: FactorObservation) -> dict[str, Any]:
    method = METHODS[factor.key]
    percentile = factor.percentile
    score = 100 * (1 - percentile if method.direction == "fear_when_high" else percentile)
    rounded_score = _round(score)
    return {
        **factor.to_dict(),
        "weight": method.weight,
        "direction": method.direction,
        "score": rounded_score,
        "contribution": _round(rounded_score * method.weight),
    }


def _score_news(news: tuple[NewsItem, ...]) -> float:
    weighted = [(item.sentiment, item.confidence * item.relevance) for item in news]
    denominator = sum(weight for _, weight in weighted)
    if denominator == 0:
        return 50.0
    mean = sum(sentiment * weight for sentiment, weight in weighted) / denominator
    return _round(50 + 50 * mean)


def _news_impact(item: NewsItem) -> tuple[float, str]:
    return (abs(item.sentiment) * item.confidence * item.relevance, item.published_at.isoformat())


def _label(score: float) -> str:
    if score <= 20:
        return "extreme_fear"
    if score <= 40:
        return "fear"
    if score <= 60:
        return "neutral"
    if score <= 80:
        return "greed"
    return "extreme_greed"


def _round(value: float) -> float:
    return round(value + 0.0, 2)


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
