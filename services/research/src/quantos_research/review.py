"""Deterministic checks for common research validity risks."""

from __future__ import annotations

from quantos_backtest import BacktestResult

from .models import CandidateResult, ResearchConfig, ReviewFinding


def review_study(
    *,
    config: ResearchConfig,
    candidates: tuple[CandidateResult, ...],
    winner: CandidateResult,
    test: BacktestResult,
    stress: BacktestResult,
) -> tuple[ReviewFinding, ...]:
    findings: list[ReviewFinding] = [
        ReviewFinding(
            "info",
            "NEXT_BAR_EXECUTION",
            "Signals execute at the next bar open, reducing same-bar look-ahead risk.",
        )
    ]
    for label, result in (
        ("train", winner.train),
        ("validation", winner.validation),
        ("test", test),
    ):
        if result.bar_count < 100:
            findings.append(
                ReviewFinding(
                    "warning",
                    "SHORT_SAMPLE",
                    f"{label} contains only {result.bar_count} bars; results may be unstable.",
                )
            )
    if test.metrics.trade_count < 5:
        findings.append(
            ReviewFinding(
                "warning",
                "FEW_TEST_TRADES",
                f"holdout test contains only {test.metrics.trade_count} completed trades.",
            )
        )
    validation_return = winner.validation.metrics.total_return
    test_return = test.metrics.total_return
    if validation_return > 0 and test_return < validation_return * 0.5:
        findings.append(
            ReviewFinding(
                "warning",
                "OUT_OF_SAMPLE_DEGRADATION",
                "holdout return is less than half the validation return.",
            )
        )
    if test.metrics.max_drawdown > 0.2:
        findings.append(
            ReviewFinding(
                "warning",
                "HIGH_DRAWDOWN",
                f"holdout maximum drawdown is {test.metrics.max_drawdown:.2%}.",
            )
        )
    if stress.metrics.total_return < test_return:
        deterioration = test_return - stress.metrics.total_return
        severity = "warning" if stress.metrics.total_return <= 0 < test_return else "info"
        findings.append(
            ReviewFinding(
                severity,
                "COST_SENSITIVITY",
                f"doubled costs reduce holdout return by {deterioration:.2%}.",
            )
        )
    fast_values = sorted({item.fast_period for item in candidates})
    slow_values = sorted({item.slow_period for item in candidates})
    if (len(fast_values) > 1 and winner.fast_period in {fast_values[0], fast_values[-1]}) or (
        len(slow_values) > 1 and winner.slow_period in {slow_values[0], slow_values[-1]}
    ):
        findings.append(
            ReviewFinding(
                "warning",
                "BOUNDARY_WINNER",
                "selected parameters lie on the search-grid boundary; expand the grid.",
            )
        )
    return tuple(findings)
