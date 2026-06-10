from __future__ import annotations

import json

import pytest

from tests.evals.categorization.scorer import score_categorization
from tests.evals.conftest import GOLDEN_DIR, SNAPSHOTS_DIR
from tests.evals.openai_interceptor import (
    InterceptorMode,
    MissingSnapshotError,
    OpenAIInterceptor,
)
from tests.evals.runner import aggregate_component
from tests.evals.snapshot import SnapshotStore

THRESHOLD_TOP_1 = 0.85
MODEL = "gpt-4o-mini"


def _load_golden() -> list[dict]:
    path = GOLDEN_DIR / "categorization.json"
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def _valid_codes() -> list[str]:
    return sorted({c["expected_category_code"] for c in _load_golden()})


def _build_prompt(merchant: str, transaction_type: str) -> str:
    codes = ", ".join(_valid_codes())
    return (
        "Suggest the most likely category for this transaction. "
        f"Merchant: {merchant}. Type: {transaction_type}. "
        f"Valid codes: {codes}. "
        'Return JSON: {"ranked": [code1, code2, code3]}'
    )


@pytest.mark.evals
async def test_categorization_quality(evals_mode: str, update_snapshots: bool) -> None:
    interceptor = OpenAIInterceptor(
        store=SnapshotStore(root=SNAPSHOTS_DIR, component="categorization"),
        mode=_resolve_mode(evals_mode, update_snapshots),
    )

    results = []
    for case in _load_golden():
        prompt = _build_prompt(case["merchant"], case["transaction_type"])
        inputs = {"merchant": case["merchant"], "type": case["transaction_type"]}

        try:
            record = await interceptor.intercept(
                prompt=prompt,
                model=MODEL,
                inputs=inputs,
                live_call=lambda p=prompt: _live_categorize(p),
            )
        except MissingSnapshotError as e:
            pytest.skip(f"snapshot miss for {case['case_id']}: {e}")

        ranked = record.response["ranked"]
        results.append(
            score_categorization(
                case_id=case["case_id"],
                expected=case["expected_category_code"],
                predicted_ranked=ranked,
                cost_usd=record.cost_usd,
            )
        )

    from tests.evals.conftest import register_component_report

    report = aggregate_component(
        name="categorization",
        metric_name="top-1",
        threshold=THRESHOLD_TOP_1,
        results=results,
    )
    register_component_report(report)

    if not report.passed:
        pytest.fail(
            f"categorization top-1={report.score:.3f} below threshold {report.threshold}. "
            f"Cases: {report.case_count}, passed: {report.pass_count}"
        )


def _resolve_mode(evals_mode: str, update_snapshots: bool) -> InterceptorMode:
    if evals_mode != "live":
        return InterceptorMode.SNAPSHOT
    return InterceptorMode.LIVE_UPDATE if update_snapshots else InterceptorMode.LIVE


async def _live_categorize(prompt: str) -> dict:
    """Real OpenAI call. Imported lazily so snapshot mode runs without `openai` configured."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    response = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)
    return {
        "response": payload,
        "tokens_prompt": response.usage.prompt_tokens if response.usage else 0,
        "tokens_completion": response.usage.completion_tokens if response.usage else 0,
        "cost_usd": _cost_from_usage(response.usage),
        "request_kwargs": {"temperature": 0, "response_format": {"type": "json_object"}},
    }


def _cost_from_usage(usage) -> float:
    if usage is None:
        return 0.0
    from tests.evals.budget import estimate_cost

    return estimate_cost(
        model=MODEL,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
    )
