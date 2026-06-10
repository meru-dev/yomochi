from __future__ import annotations

from tests.evals.runner import CaseResult


def score_categorization(
    *,
    case_id: str,
    expected: str,
    predicted_ranked: list[str],
    cost_usd: float,
) -> CaseResult:
    """Score one categorization case. `passed` = expected appears at index 0."""
    rank: int | None = None
    for i, code in enumerate(predicted_ranked[:3], start=1):
        if code == expected:
            rank = i
            break
    in_top_3 = rank is not None
    passed = rank == 1
    score = 1.0 if passed else 0.0
    return CaseResult(
        case_id=case_id,
        passed=passed,
        score=score,
        cost_usd=cost_usd,
        details={
            "expected": expected,
            "predicted_top_3": predicted_ranked[:3],
            "rank": rank,
            "in_top_3": in_top_3,
        },
    )
