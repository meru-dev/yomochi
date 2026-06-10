from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.application.insights.ports.ai_insight_client import InsightRequest, InsightResponse
from app.domain.value_objects.enums import Period
from app.outbound.adapters.openai._gateway import OpenAIGateway
from app.outbound.adapters.openai.pricing import estimate_cost
from app.outbound.observability.prometheus import openai_cost_usd_total, openai_tokens_total

_MONTH_NAMES = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

_SYSTEM_PROMPT = """\
You are a personal finance analyst. Analyze the user's financial data and provide \
clear, actionable insights. Be concise and specific — focus on real patterns, name \
actual categories and merchants from the provided data. Avoid generic advice. \
Never recommend or mention external apps, services, or financial tools (e.g. Mint, YNAB, budgeting apps).\
"""


class _InsightOutput(BaseModel):
    title: str = Field(description="Short title (max 10 words) summarising the key finding")
    description: str = Field(
        description="2-4 paragraph analysis mentioning specific categories and merchants"
    )
    impact_score: int = Field(ge=1, le=10, description="Severity/relevance on a 1-10 scale")


def _build_user_prompt(request: InsightRequest) -> str:
    if request.period == Period.MONTHLY:
        period_label = f"{_MONTH_NAMES[request.period_month]} {request.period_year}"
    else:
        period_label = f"Week {request.period_month}, {request.period_year}"

    chunk_sections = []
    for chunk in request.chunks:
        chunk_sections.append(f"[{chunk.period_label} — {chunk.chunk_type}]\n{chunk.content}")

    context = "\n\n".join(chunk_sections) if chunk_sections else "No historical data available."
    user_q = f"\nUser question: {request.user_question}" if request.user_question else ""

    return (
        f"Please analyze my finances for {period_label}.\n\n"
        f"Context from financial history:\n{context}"
        f"{user_q}"
    )


class OpenAIInsightClient:
    def __init__(
        self,
        gateway: OpenAIGateway,
        model: str,
        read_timeout_seconds: float,
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._timeout = read_timeout_seconds

    async def generate(self, request: InsightRequest) -> InsightResponse:
        return await self._gateway.call(
            endpoint="chat",
            timeout=self._timeout,
            fn=lambda client: self._do_generate(client, request),
        )

    async def _do_generate(self, client: AsyncOpenAI, request: InsightRequest) -> InsightResponse:
        response = await client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(request)},
            ],
            response_format=_InsightOutput,
            temperature=0.4,
            max_tokens=1000,
        )
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        openai_tokens_total.labels(endpoint="chat", direction="prompt").inc(prompt_tokens)
        openai_tokens_total.labels(endpoint="chat", direction="completion").inc(completion_tokens)
        cost = estimate_cost(
            self._model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        )
        openai_cost_usd_total.labels(endpoint="chat", model=self._model).inc(cost)

        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI returned no parsed structured output")
        return InsightResponse(
            title=parsed.title,
            description=parsed.description,
            impact_score=parsed.impact_score,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
