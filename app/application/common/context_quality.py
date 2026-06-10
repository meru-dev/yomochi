from app.application.common.ports.chunk_retriever import RetrievedChunk
from app.domain.value_objects.enums import ContextQuality


def assess_quality(chunks: list[RetrievedChunk]) -> ContextQuality:
    has_monthly = any(c.chunk_type == "monthly_summary" for c in chunks)
    has_shift = any(c.chunk_type == "behavioral_shift" for c in chunks)
    if has_monthly and has_shift:
        return ContextQuality.FULL
    if has_monthly or has_shift:
        return ContextQuality.PARTIAL
    return ContextQuality.NONE
