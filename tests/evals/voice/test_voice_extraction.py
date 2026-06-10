from __future__ import annotations

import os

import pytest


@pytest.mark.evals
def test_voice_extraction_quality() -> None:
    if os.getenv("EVALS_INCLUDE_VOICE") != "1":
        pytest.skip("voice evals gated; set EVALS_INCLUDE_VOICE=1 after P3.A lands")
    pytest.skip("voice extractor not yet implemented (P3.A pending)")
