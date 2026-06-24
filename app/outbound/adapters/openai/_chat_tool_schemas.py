"""OpenAI function (tool) schemas for the chat function-calling path (Task 4b).

These map 1:1 to the five ``ChatTools`` methods. The model only ever supplies
the typed parameters declared here — never free-form SQL — which is the
determinism/auditability guarantee from Plan 4. ``user_id`` is deliberately
NOT exposed as a parameter: the use case binds it server-side in the tool
executor, so the model cannot select another user's data.
"""

from typing import Any

TOOL_NAMES: frozenset[str] = frozenset(
    {
        "get_month_summary",
        "get_category_trend",
        "get_spend_window",
        "get_user_profile",
        "search_transactions",
        "list_categories",
    }
)


def _fn(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


CHAT_TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn(
        "get_month_summary",
        "Per-currency income, expenses, savings rate and top categories for one "
        "calendar month. Use for 'how much did I spend/earn/save in <month>'.",
        {
            "year": {"type": "integer", "description": "Four-digit calendar year, e.g. 2026."},
            "month": {
                "type": "integer",
                "description": "Month number 1-12.",
                "minimum": 1,
                "maximum": 12,
            },
        },
        ["year", "month"],
    ),
    _fn(
        "get_category_trend",
        "Month-over-month EXPENSE series for one named category, n_months back "
        "from today. Use for 'how has my <category> spending changed'.",
        {
            "category": {"type": "string", "description": "Exact category name, e.g. 'Food'."},
            "n_months": {
                "type": "integer",
                "description": "Number of trailing months to include.",
                "minimum": 1,
                "maximum": 24,
            },
        },
        ["category", "n_months"],
    ),
    _fn(
        "get_spend_window",
        "Totals and per-category breakdown over an arbitrary date range. Use for "
        "'what did I spend between <start> and <end>'.",
        {
            "start_date": {
                "type": "string",
                "description": "Inclusive ISO-8601 date, e.g. 2026-01-01.",
            },
            "end_date": {
                "type": "string",
                "description": "Inclusive ISO-8601 date, e.g. 2026-01-31.",
            },
        },
        ["start_date", "end_date"],
    ),
    _fn(
        "get_user_profile",
        "Four-month rolling aggregate of the user's finances. Call this first for "
        "broad 'how am I doing' questions to ground the answer.",
        {},
        [],
    ),
    _fn(
        "search_transactions",
        "Fuzzy text match on merchant/notes to find specific charges. Use for "
        "'find that charge from <merchant>' style questions.",
        {
            "text": {
                "type": "string",
                "description": "Substring to fuzzy-match on merchant or notes.",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of matches to return.",
                "minimum": 1,
                "maximum": 50,
            },
        },
        ["text", "limit"],
    ),
    _fn(
        "list_categories",
        "Returns all category names the user has assigned to transactions, "
        "with their type (expense/income) and transaction count (most-used first). "
        "Call this to discover exact category names before using get_category_trend "
        "or any category filter when you are unsure of the correct spelling.",
        {},
        [],
    ),
]
