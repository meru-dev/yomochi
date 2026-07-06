from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class InsightContextChunk:
    """Deterministic insight-context DTO fed to the AI insight client.

    Built by the deterministic context builder (`_process_insight_steps`) from SQL
    aggregations — NOT a retrieval/ANN type. Carries the formatted text plus light
    metadata the prompt template renders (period label + chunk type).
    """

    content: str
    chunk_type: str  # "monthly_summary" | "behavioral_shift"
    period_label: str
    metadata: dict[str, Any]
