from __future__ import annotations

import re
from dataclasses import dataclass


def check_impact_score_range(*, score: int, allowed: tuple[int, int]) -> bool:
    low, high = allowed
    return low <= score <= high


_FX_PATTERN = re.compile(
    r"(?:in|spent|paid|combined)\s+\w+\s+(?:in|and)\s+\w+\s+(?:combined|together)",
    re.IGNORECASE,
)


def check_no_fx_summed_total(text: str) -> bool:
    """Returns True when the text does NOT contain a phrase that sums across currencies."""
    if _FX_PATTERN.search(text):
        return False
    suspicious = ["JPY and EUR combined", "USD and JPY total", "all currencies combined"]
    return not any(s.lower() in text.lower() for s in suspicious)


def check_no_hallucinated_merchant(text: str, *, allowed: list[str]) -> bool:
    """Naïve: every capitalised multi-word phrase that looks like a merchant must be in allowed."""
    candidates = re.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+\b", text)
    return all(c in allowed for c in candidates)


@dataclass(frozen=True, slots=True)
class DeterministicChecks:
    impact_score_passed: bool
    no_fx_summed: bool
    no_hallucinated_merchant: bool

    @property
    def all_passed(self) -> bool:
        return self.impact_score_passed and self.no_fx_summed and self.no_hallucinated_merchant
