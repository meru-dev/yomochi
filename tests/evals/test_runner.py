from __future__ import annotations

import pytest

from tests.evals.runner import CaseResult, aggregate_component


def test_aggregate_empty_yields_zero_pass_rate() -> None:
    report = aggregate_component(name="search", metric_name="recall@3", threshold=0.7, results=[])
    assert report.name == "search"
    assert report.passed is False  # nothing ran; treat as fail
    assert report.score == 0.0


def test_aggregate_pass_rate_across_cases() -> None:
    results = [
        CaseResult(case_id="c1", passed=True, score=1.0, cost_usd=0.001, details={}),
        CaseResult(case_id="c2", passed=False, score=0.0, cost_usd=0.001, details={}),
        CaseResult(case_id="c3", passed=True, score=1.0, cost_usd=0.001, details={}),
    ]
    report = aggregate_component(
        name="categorization", metric_name="top-1", threshold=0.5, results=results
    )
    assert report.score == pytest.approx(2 / 3)
    assert report.passed is True
    assert report.total_cost_usd == pytest.approx(0.003)


def test_aggregate_continuous_metric_averages() -> None:
    results = [
        CaseResult(case_id="q1", passed=True, score=0.8, cost_usd=0.0, details={}),
        CaseResult(case_id="q2", passed=False, score=0.4, cost_usd=0.0, details={}),
    ]
    report = aggregate_component(
        name="search",
        metric_name="recall@3",
        threshold=0.7,
        results=results,
        score_mode="mean",
    )
    assert report.score == pytest.approx(0.6)
    assert report.passed is False  # 0.6 < 0.7
