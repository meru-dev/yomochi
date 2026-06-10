from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from tests.evals.snapshot import SnapshotRecord, SnapshotStore, snapshot_key


class MissingSnapshotError(RuntimeError):
    pass


class InterceptorMode(StrEnum):
    SNAPSHOT = "snapshot"
    LIVE = "live"  # call through; compare with existing snapshot, log diff, keep existing
    LIVE_UPDATE = "live_update"  # call through; overwrite snapshot


LiveCall = Callable[[], Awaitable[dict[str, Any]]]


class OpenAIInterceptor:
    """Bridges between production OpenAI adapters and evals snapshot store.

    Production code passes its prompt + model + inputs through `.intercept(...)`
    and receives back a SnapshotRecord. In snapshot mode the response is read
    from disk; in live mode it's fetched via the provided `live_call`.
    """

    def __init__(self, *, store: SnapshotStore, mode: InterceptorMode) -> None:
        self._store = store
        self._mode = mode

    async def intercept(
        self,
        *,
        prompt: str,
        model: str,
        inputs: dict[str, Any],
        live_call: LiveCall,
    ) -> SnapshotRecord:
        key = snapshot_key(prompt=prompt, model=model, inputs=inputs)

        if self._mode is InterceptorMode.SNAPSHOT:
            record = self._store.load(key)
            if record is None:
                raise MissingSnapshotError(
                    f"No snapshot for key={key} (component={self._store_component()}). "
                    "Run with EVALS_LIVE=1 EVALS_UPDATE_SNAPSHOTS=1 to capture."
                )
            return record

        # LIVE or LIVE_UPDATE
        result = await live_call()
        existing = self._store.load(key)
        record = SnapshotRecord(
            key=key,
            prompt=prompt,
            model=model,
            request_kwargs=result.get("request_kwargs", {}),
            response=result["response"],
            tokens_prompt=result["tokens_prompt"],
            tokens_completion=result["tokens_completion"],
            cost_usd=result["cost_usd"],
            captured_at=SnapshotStore.now_iso(),
        )

        if self._mode is InterceptorMode.LIVE_UPDATE or existing is None:
            self._store.save(record)

        return record

    def _store_component(self) -> str:
        return self._store.component
