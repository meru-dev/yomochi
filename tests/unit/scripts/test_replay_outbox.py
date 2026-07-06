"""The replay_outbox CLI must refuse to act without an explicit selector."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.replay_outbox import main


def test_refuses_without_selector() -> None:
    # No --id / --event-type / --all → argparse error → SystemExit(2); never runs.
    with (
        patch("sys.argv", ["replay_outbox", "--dry-run"]),
        patch("scripts.replay_outbox._run") as run,
        patch("scripts.replay_outbox.asyncio.run"),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 2
    run.assert_not_called()


@pytest.mark.parametrize(
    "argv",
    [
        ["--all"],
        ["--id", "00000000-0000-0000-0000-000000000001"],
        ["--event-type", "InsightRequested"],
        ["--all", "--dry-run", "--min-age-minutes", "10", "--limit", "5"],
    ],
)
def test_accepts_with_selector(argv: list[str]) -> None:
    # A valid selector passes the guard and reaches the runner. Patch `_run` (so no
    # coroutine is created) and `asyncio.run` (no-op) to keep the test offline.
    with (
        patch("sys.argv", ["replay_outbox", *argv]),
        patch("scripts.replay_outbox._run", MagicMock()) as run,
        patch("scripts.replay_outbox.asyncio.run"),
    ):
        main()
    run.assert_called_once()
