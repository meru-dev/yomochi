from openai import AsyncOpenAI

from app.outbound.adapters.openai._gateway import OpenAIGateway
from app.outbound.adapters.openai.pricing import estimate_cost
from app.outbound.observability.prometheus import openai_cost_usd_total, openai_tokens_total


class OpenAITextEmbedder:
    def __init__(
        self,
        gateway: OpenAIGateway,
        model: str,
        read_timeout_seconds: float,
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._timeout = read_timeout_seconds

    async def embed(self, text: str) -> list[float]:
        result = await self.embed_batch([text])
        return result[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._gateway.call(
            endpoint="embeddings",
            timeout=self._timeout,
            fn=lambda client: self._do_embed(client, texts),
        )

    async def _do_embed(self, client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
        response = await client.embeddings.create(model=self._model, input=texts)
        total_tokens = response.usage.total_tokens if response.usage else 0
        openai_tokens_total.labels(endpoint="embeddings", direction="total").inc(total_tokens)
        cost = estimate_cost(self._model, prompt_tokens=total_tokens)
        openai_cost_usd_total.labels(endpoint="embeddings", model=self._model).inc(cost)
        return [item.embedding for item in response.data]
