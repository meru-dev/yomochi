from __future__ import annotations

import pytest

from tests.evals.insights.judge import parse_judge_response


def test_parse_all_yes_passes() -> None:
    raw = '{"q1": "Y", "q2": "Y", "q4": "Y", "q5": "Y", "q6": "Y"}'
    verdict = parse_judge_response(raw)
    assert verdict.all_passed is True
    assert verdict.items["q1"] is True


def test_parse_any_no_fails() -> None:
    raw = '{"q1": "Y", "q2": "N", "q4": "Y", "q5": "Y", "q6": "Y"}'
    verdict = parse_judge_response(raw)
    assert verdict.all_passed is False
    assert verdict.items["q2"] is False


def test_parse_malformed_raises() -> None:
    with pytest.raises(ValueError):
        parse_judge_response("not json")
