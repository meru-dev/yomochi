import json
import os
from pathlib import Path

import pytest
from httpx import AsyncClient

_GOLDEN_FILE = Path(__file__).parent / "golden.jsonl"
_SKIP_REASON = "Set RUN_EVALS=1 to run evals (costs OpenAI credits)"

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_EVALS"),
    reason=_SKIP_REASON,
)


def _load_golden() -> list[dict]:
    return [json.loads(line) for line in _GOLDEN_FILE.read_text().splitlines() if line.strip()]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _load_golden(), ids=[c["question"][:40] for c in _load_golden()])
async def test_chat_answer_contains_expected_terms(case: dict, client: AsyncClient) -> None:
    """Each golden question must produce an answer containing at least one expected term."""
    resp = await client.post("/api/v1/chat", json={"message": case["question"]}, timeout=60.0)
    assert resp.status_code == 200, resp.text

    answer = resp.json()["answer"].lower()
    terms = [t.lower() for t in case["must_contain_any"]]
    assert any(t in answer for t in terms), (
        f"Answer contains none of {case['must_contain_any']}.\n"
        f"Question: {case['question']}\n"
        f"Answer: {resp.json()['answer']}"
    )
