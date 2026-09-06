"""Live integration test against a real Qdrant instance and the real OpenAI
embeddings API. Skipped entirely if either isn't reachable/configured --
this is deliberately not mocked: the whole point is checking that the
actual embedded corpus retrieves the actual priority sections for a
realistic query, which a mock of either service couldn't tell us.

Costs a handful of embedding-API calls (a few cents at most) when it does
run. Requires `docker compose up -d qdrant` and OPENAI_API_KEY set, plus
`python scripts/embed_corpus.py` having been run at least once.
"""

from __future__ import annotations

import httpx
import pytest

from gstrecon.rag.config import get_settings
from gstrecon.rag.retrieval.vector_store import similarity_search


def _qdrant_reachable() -> bool:
    try:
        settings = get_settings()
    except Exception:
        return False
    try:
        response = httpx.get(f"{settings.qdrant_url}/healthz", timeout=2.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def _openai_key_configured() -> bool:
    try:
        return bool(get_settings().openai_api_key)
    except Exception:
        return False


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (_qdrant_reachable() and _openai_key_configured()),
        reason="Qdrant not reachable or OPENAI_API_KEY not set -- see module docstring",
    ),
]


class TestLiveRetrieval:
    @pytest.mark.asyncio
    async def test_blocked_credit_query_retrieves_section_17(self) -> None:
        results = await similarity_search(
            "input tax credit blocked for motor vehicles", top_k=5
        )
        assert results, "collection is empty -- run scripts/embed_corpus.py first"
        citations = [r.chunk.citation for r in results]
        assert any("Section 17" in c for c in citations)

    @pytest.mark.asyncio
    async def test_non_payment_reversal_query_retrieves_rule_37(self) -> None:
        results = await similarity_search(
            "reversal of input tax credit when payment not made to supplier", top_k=5
        )
        citations = [r.chunk.citation for r in results]
        assert any("Section 37" in c for c in citations)

    @pytest.mark.asyncio
    async def test_off_topic_query_returns_nothing_above_the_floor(self) -> None:
        # The whole point of the similarity floor: an unrelated query should
        # surface no citation at all, not a fluent-sounding wrong one.
        results = await similarity_search("recipe for chocolate cake", top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_every_result_respects_the_configured_floor(self) -> None:
        results = await similarity_search("eligibility to take credit on capital goods", top_k=5)
        floor = get_settings().similarity_floor
        assert all(r.score >= floor for r in results)
