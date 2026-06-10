from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.evals.conftest import GOLDEN_DIR
from tests.evals.runner import CaseResult, aggregate_component

THRESHOLD_RUBRIC_PASS_RATE = 0.85


def _load_golden() -> list[dict]:
    return json.loads((GOLDEN_DIR / "insights.json").read_text(encoding="utf-8"))["cases"]


def _fixture_dir() -> Path:
    return Path("tests/fixtures/personas")


@pytest.mark.evals
async def test_insight_quality(evals_mode: str, update_snapshots: bool) -> None:
    if not _fixture_dir().exists():
        pytest.skip("insights evals require persona fixtures from P1.B (seed-demo)")

    pytest.skip(
        "insight executor wiring activates once persona fixtures"
        " + ProcessInsightUseCase are available"
    )

    results: list[CaseResult] = []
    report = aggregate_component(
        name="insights",
        metric_name="rubric pass rate",
        threshold=THRESHOLD_RUBRIC_PASS_RATE,
        results=results,
    )
    if not report.passed:
        pytest.fail(f"insights rubric pass rate {report.score:.3f} below {report.threshold}")
