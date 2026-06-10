from dataclasses import dataclass


@dataclass(frozen=True)
class InsightWorkerConfig:
    min_transactions_for_insight: int = 3
