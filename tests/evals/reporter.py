from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from tests.evals.runner import ComponentReport


@dataclass(frozen=True, slots=True)
class RunReport:
    date: str
    components: list[ComponentReport]
    total_cost_usd: float
    mode: str
    notes: list[str] = field(default_factory=list)


def write_reports(run: RunReport, *, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{run.date}.md"
    json_path = output_dir / f"{run.date}.json"

    md_path.write_text(_render_markdown(run), encoding="utf-8")
    json_path.write_text(_render_json(run), encoding="utf-8")
    return md_path, json_path


def _render_markdown(run: RunReport) -> str:
    lines = [
        f"# Evals Report — {run.date}",
        "",
        f"_Mode: {run.mode} · Total cost: ${run.total_cost_usd:.4f}_",
        "",
    ]
    for c in run.components:
        status = "✓" if c.passed else "✗"
        lines.extend(
            [
                f"## {c.name.title()}",
                "",
                "| Metric | Value | Threshold | Status |",
                "| --- | --- | --- | --- |",
                f"| {c.metric_name} | {c.score:.3f} | {c.threshold:.2f} | {status} |",
                "",
                f"_Cases: {c.case_count} · Passed: {c.pass_count} · Cost: ${c.total_cost_usd:.4f}_",
                "",
            ]
        )
    if run.notes:
        lines.append("## Notes")
        lines.extend(f"- {n}" for n in run.notes)
    return "\n".join(lines)


def _render_json(run: RunReport) -> str:
    payload = {
        "date": run.date,
        "mode": run.mode,
        "total_cost_usd": run.total_cost_usd,
        "components": [
            {
                "name": c.name,
                "metric_name": c.metric_name,
                "threshold": c.threshold,
                "score": c.score,
                "passed": c.passed,
                "case_count": c.case_count,
                "pass_count": c.pass_count,
                "total_cost_usd": c.total_cost_usd,
            }
            for c in run.components
        ],
        "notes": run.notes,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
