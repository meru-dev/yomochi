from __future__ import annotations

import json
from typing import TYPE_CHECKING

from tests.evals.reporter import RunReport, write_reports
from tests.evals.runner import ComponentReport

if TYPE_CHECKING:
    from pathlib import Path


def _make_report(name: str, score: float, threshold: float, passed: bool) -> ComponentReport:
    return ComponentReport(
        name=name,
        metric_name="metric",
        threshold=threshold,
        score=score,
        passed=passed,
        case_count=10,
        pass_count=int(score * 10),
        total_cost_usd=0.05,
    )


def test_write_reports_creates_md_and_json(tmp_path: Path) -> None:
    run = RunReport(
        date="2026-05-20",
        components=[
            _make_report("insights", 0.90, 0.85, True),
            _make_report("search", 0.65, 0.70, False),
        ],
        total_cost_usd=0.10,
        mode="snapshot",
    )
    md_path, json_path = write_reports(run, output_dir=tmp_path)

    md = md_path.read_text(encoding="utf-8")
    assert "Insights" in md
    assert "0.900" in md or "0.9" in md
    assert "✓" in md  # insights passed
    assert "✗" in md  # search failed

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["date"] == "2026-05-20"
    assert payload["components"][0]["name"] == "insights"
    assert payload["components"][1]["passed"] is False
