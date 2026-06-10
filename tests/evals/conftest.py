from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.evals.reporter import RunReport, write_reports

if TYPE_CHECKING:
    from tests.evals.runner import ComponentReport

EVALS_DIR = Path(__file__).parent
GOLDEN_DIR = EVALS_DIR / "golden"
SNAPSHOTS_DIR = EVALS_DIR / "snapshots"
RESULTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "evals" / "results"


@pytest.fixture(scope="session")
def evals_mode() -> str:
    return "live" if os.getenv("EVALS_LIVE") == "1" else "snapshot"


@pytest.fixture(scope="session")
def update_snapshots() -> bool:
    return os.getenv("EVALS_UPDATE_SNAPSHOTS") == "1"


_collected_reports: list[ComponentReport] = []


def register_component_report(report: ComponentReport) -> None:
    _collected_reports.append(report)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not any("evals" in (m.name for m in item.iter_markers()) for item in session.items):
        return
    if not _collected_reports:
        return

    date = datetime.now(UTC).strftime("%Y-%m-%d")
    mode = "live" if os.getenv("EVALS_LIVE") == "1" else "snapshot"
    total = sum(c.total_cost_usd for c in _collected_reports)
    run = RunReport(
        date=date,
        components=list(_collected_reports),
        total_cost_usd=total,
        mode=mode,
    )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    md, js = write_reports(run, output_dir=RESULTS_DIR)
    print(f"\nEvals report written: {md} and {js}", flush=True)
