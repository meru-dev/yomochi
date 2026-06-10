from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Literal

ScoreMode = Literal["pass_rate", "mean"]


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    passed: bool
    score: float
    cost_usd: float
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ComponentReport:
    name: str
    metric_name: str
    threshold: float
    score: float
    passed: bool
    case_count: int
    pass_count: int
    total_cost_usd: float
    cases: tuple[CaseResult, ...] = field(default=())


def aggregate_component(
    *,
    name: str,
    metric_name: str,
    threshold: float,
    results: list[CaseResult],
    score_mode: ScoreMode = "pass_rate",
) -> ComponentReport:
    if not results:
        return ComponentReport(
            name=name,
            metric_name=metric_name,
            threshold=threshold,
            score=0.0,
            passed=False,
            case_count=0,
            pass_count=0,
            total_cost_usd=0.0,
        )

    if score_mode == "mean":
        score = mean(r.score for r in results)
    else:
        score = sum(1 for r in results if r.passed) / len(results)

    return ComponentReport(
        name=name,
        metric_name=metric_name,
        threshold=threshold,
        score=score,
        passed=score >= threshold,
        case_count=len(results),
        pass_count=sum(1 for r in results if r.passed),
        total_cost_usd=sum(r.cost_usd for r in results),
        cases=tuple(results),
    )
