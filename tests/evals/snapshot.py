from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def snapshot_key(*, prompt: str, model: str, inputs: dict[str, Any]) -> str:
    """Deterministic 16-char hex key derived from prompt + model + inputs."""
    payload = json.dumps(
        {"prompt": prompt, "model": model, "inputs": inputs},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    key: str
    prompt: str
    model: str
    request_kwargs: dict[str, Any]
    response: dict[str, Any]
    tokens_prompt: int
    tokens_completion: int
    cost_usd: float
    captured_at: str


class SnapshotStore:
    """On-disk snapshot store; each component (insights/search/...) gets its own subdir."""

    def __init__(self, root: str | Path, component: str) -> None:
        from pathlib import Path as PathlibPath

        self._dir = PathlibPath(root) / component
        self._dir.mkdir(parents=True, exist_ok=True)
        self._component = component

    def load(self, key: str) -> SnapshotRecord | None:
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return SnapshotRecord(**data)

    def save(self, record: SnapshotRecord) -> None:
        path = self._dir / f"{record.key}.json"
        path.write_text(
            json.dumps(asdict(record), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @property
    def component(self) -> str:
        """Get the component name."""
        return self._component

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")
