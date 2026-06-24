"""Tool-executor closure for the function-calling chat path (Task 4b).

The use case builds an async ``tool_executor(name, args)`` closing over the
injected ``ChatTools`` impl and the request ``user_id``. The OpenAI adapter
dispatches model tool calls through it; this is the per-user isolation boundary
— ``user_id`` is bound here, never supplied by the model.

Results are passed through ``to_jsonable`` so they are safe for ``json.dumps``
in the adapter's tool-role messages.
"""

from datetime import date
from typing import Any

from app.application.chat.ports.chat_ai_client import ToolExecutor
from app.application.chat.ports.chat_tools import ChatTools, to_jsonable
from app.domain.value_objects.ids import UserId


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def build_tool_executor(tools: ChatTools, user_id: UserId) -> ToolExecutor:
    """Return an async (name, args) -> json-serialisable dict dispatcher.

    user_id is bound server-side: the model never selects whose data it reads.
    Unknown tool names and bad arguments surface as an error payload (data the
    model can react to) rather than raising into the OpenAI loop.
    """
    uid = str(user_id)

    async def _execute(name: str, args: dict[str, Any]) -> Any:
        try:
            result: Any
            if name == "get_month_summary":
                result = await tools.get_month_summary(
                    uid, year=int(args["year"]), month=int(args["month"])
                )
            elif name == "get_category_trend":
                result = await tools.get_category_trend(
                    uid, category=str(args["category"]), n_months=int(args["n_months"])
                )
            elif name == "get_spend_window":
                result = await tools.get_spend_window(
                    uid,
                    start_date=_parse_date(args["start_date"]),
                    end_date=_parse_date(args["end_date"]),
                )
            elif name == "get_user_profile":
                result = await tools.get_user_profile(uid)
            elif name == "search_transactions":
                result = await tools.search_transactions(
                    uid, text=str(args["text"]), limit=int(args["limit"])
                )
            elif name == "list_categories":
                result = await tools.list_categories(uid)
            else:
                return {"error": f"unknown tool: {name}"}
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": f"invalid arguments for {name}: {exc}"}
        return to_jsonable(result)

    return _execute


def tools_metadata(tools_used: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    """JSON-safe chunks_used payload for tools mode: which tools were invoked."""
    return tuple({"tool": name} for name in tools_used)
