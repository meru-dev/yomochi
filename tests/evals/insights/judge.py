from __future__ import annotations

import json
from dataclasses import dataclass

JUDGE_MODEL = "gpt-4o"

JUDGE_PROMPT_TEMPLATE = """\
You are evaluating one monthly spending insight against fixed criteria.

Insight body:
{insight_text}

BudgetSummary used:
{summary_json}

Categories present in input: {categories}
Merchants present in input: {merchants}
ContextQuality declared: {context_quality}

Answer each item strictly Y or N. Do not explain. Return only JSON.

q1. mentions_input_category: at least one category from the input list named?
q2. mentions_input_merchant: at least one merchant from the input list named?
q4. tone_descriptive: tone is descriptive (no "should", "must", "try to",
   "recommend", "consider")?
q5. acknowledges_partial_when_needed: if ContextQuality is PARTIAL or NONE,
   does the text acknowledge limited data? (Return Y if ContextQuality is FULL.)
q6. no_hallucinated_merchant: every merchant named in the text exists in the
   input merchant list?

Return: {{"q1": "Y|N", "q2": "Y|N", "q4": "Y|N", "q5": "Y|N", "q6": "Y|N"}}
"""


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    items: dict[str, bool]

    @property
    def all_passed(self) -> bool:
        return all(self.items.values())


def parse_judge_response(raw: str) -> JudgeVerdict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Judge response is not JSON: {raw}") from e

    items = {}
    for k, v in data.items():
        if v not in ("Y", "N"):
            raise ValueError(f"Judge item {k} returned {v!r}; expected Y/N")
        items[k] = v == "Y"
    return JudgeVerdict(items=items)


def build_judge_prompt(
    *,
    insight_text: str,
    summary_json: str,
    categories: list[str],
    merchants: list[str],
    context_quality: str,
) -> str:
    return JUDGE_PROMPT_TEMPLATE.format(
        insight_text=insight_text,
        summary_json=summary_json,
        categories=", ".join(categories),
        merchants=", ".join(merchants),
        context_quality=context_quality,
    )
