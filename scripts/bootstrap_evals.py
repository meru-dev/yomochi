from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from textwrap import dedent

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[1]
DRAFT_DIR = ROOT / "tests" / "evals" / "golden" / ".draft"


CATEGORIZATION_META_PROMPT = dedent(
    """\
    Generate 100 (merchant, transaction_type, expected_category_code) examples
    for a Japanese personal finance app. The user travels and shops in JP, US, EU.
    Categories available: food, konbini, transport, shopping, housing, entertainment,
    salary, healthcare, utilities, travel, education, gifts, subscriptions, groceries.
    Include JP merchants (Lawson, FamilyMart, JR East, Yamada Denki, Mos Burger),
    US/EU merchants (Amazon, Starbucks, Uber, Spotify).
    Mix EXPENSE and INCOME.
    Return JSON: {"cases": [{"case_id": "cat_001", "merchant": "...",
      "transaction_type": "EXPENSE", "expected_category_code": "..."}, ...]}.
    """
)

SEARCH_META_PROMPT = dedent(
    """\
    Generate 50 natural-language search queries about personal transactions plus
    the transaction IDs each should match. Use the persona's transaction fixtures
    (placeholder IDs: meiko_tx_001..meiko_tx_180). Cover: time-window queries,
    merchant queries, category queries, amount queries, multi-currency queries.
    Return JSON: {"cases": [{"case_id": "search_001", "query": "...",
      "expected_transaction_ids": ["meiko_tx_042"]}, ...]}.
    """
)

INSIGHTS_META_PROMPT = dedent(
    """\
    Generate 20 evaluation scenarios for monthly spending insights. Each case
    describes a transaction pattern and what an ideal insight must (and must not)
    say. Cover: normal month, multi-currency split, first-week PARTIAL context,
    insufficient data NONE, high-impact category shift, recurring/subscription
    spike. Avoid LLM-isms like "should reduce spending" — Yomochi insights are
    descriptive, not prescriptive.
    Return JSON per the schema in tests/evals/golden/insights.json.
    """
)

META_PROMPTS = {
    "categorization": CATEGORIZATION_META_PROMPT,
    "search": SEARCH_META_PROMPT,
    "insights": INSIGHTS_META_PROMPT,
}


async def bootstrap(component: str, persona: str | None) -> None:
    if component not in META_PROMPTS:
        print(f"Unknown component: {component}", file=sys.stderr)
        sys.exit(2)

    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    prompt = META_PROMPTS[component]
    if persona:
        prompt += f"\n\nPersona context: {persona}"

    client = AsyncOpenAI()
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)

    out_name = f"{component}_{persona or 'default'}.json"
    out_path = DRAFT_DIR / out_name
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(payload.get('cases', []))} cases to {out_path}")
    print("Review and promote to tests/evals/golden/<component>.json when ready.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap golden evals cases.")
    parser.add_argument(
        "--component",
        required=True,
        choices=["insights", "search", "categorization"],
    )
    parser.add_argument("--persona", default=None)
    args = parser.parse_args()
    asyncio.run(bootstrap(args.component, args.persona))


if __name__ == "__main__":
    main()
