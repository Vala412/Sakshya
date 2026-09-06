"""Offline unit tests for the explanation layer -- similarity_search and the
LLM call are both mocked, so these run fast and free, and exercise every
branch (out-of-scope code, guardrail fallback, grounded explanation,
generation failure) without needing Qdrant or an OpenAI key.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import openai
import pytest

from gstrecon.exceptions import Exception_, ReasonCode, Severity
from gstrecon.matching import MatchCategory
from gstrecon.rag.corpus.chunker import LawChunk
from gstrecon.rag.generation import explain
from gstrecon.rag.generation.explain import (
    GENERATION_FAILED_MESSAGE,
    NO_CITATION_MESSAGE,
    ExplanationResult,
    explain_finding,
    explain_findings,
)
from gstrecon.rag.generation.prompts import RETRIEVAL_QUERIES
from gstrecon.rag.retrieval.vector_store import RetrievedChunk


def _finding(reason_code: ReasonCode) -> Exception_:
    return Exception_(
        reason_code=reason_code,
        severity=Severity.HIGH,
        description="test description",
        match_category=MatchCategory.UNMATCHED,
        books_doc=None,
        gstr2b_doc=None,
        itc_at_risk=Decimal("180.00"),
        evidence="test evidence",
    )


def _retrieved(section_number: str = "16", score: float = 0.6) -> RetrievedChunk:
    chunk = LawChunk(
        source_document="CGST Act",
        chapter="Chapter V: INPUT TAX CREDIT",
        section_number=section_number,
        section_title="Eligibility and conditions for taking input tax credit",
        text="Every registered person shall be entitled to take credit of input tax.",
    )
    return RetrievedChunk(chunk=chunk, score=score)


class TestScopeFilter:
    def test_out_of_scope_reason_code_returns_none(self) -> None:
        # EX-02 is LOW severity / zero ITC impact -- deliberately excluded
        # from RETRIEVAL_QUERIES, see prompts.py's docstring.
        assert ReasonCode.EX_02 not in RETRIEVAL_QUERIES

    @pytest.mark.asyncio
    async def test_explain_finding_returns_none_for_out_of_scope_code(self) -> None:
        result = await explain_finding(_finding(ReasonCode.EX_02))
        assert result is None

    def test_every_high_and_medium_severity_code_has_a_query(self) -> None:
        from gstrecon.exceptions import _SEVERITY

        for code, severity in _SEVERITY.items():
            if severity in (Severity.HIGH, Severity.MEDIUM):
                assert code in RETRIEVAL_QUERIES, f"{code} should have a retrieval query"
            else:
                assert code not in RETRIEVAL_QUERIES, f"{code} should NOT have a retrieval query"


class TestGuardrail:
    @pytest.mark.asyncio
    async def test_no_results_produces_fallback_not_a_model_call(self, monkeypatch) -> None:
        search_mock = AsyncMock(return_value=[])
        chat_mock = AsyncMock()
        monkeypatch.setattr(explain, "similarity_search", search_mock)
        monkeypatch.setattr(explain, "chat", chat_mock)

        result = await explain_finding(_finding(ReasonCode.EX_09))

        assert result == ExplanationResult(
            reason_code=ReasonCode.EX_09,
            explanation=NO_CITATION_MESSAGE,
            citations=[],
            grounded=False,
        )
        # The whole point of the guardrail: no citation means no API spend.
        chat_mock.assert_not_called()


class TestGroundedExplanation:
    @pytest.mark.asyncio
    async def test_successful_generation_is_grounded_with_citations(self, monkeypatch) -> None:
        retrieved = [_retrieved()]
        search_mock = AsyncMock(return_value=retrieved)

        class _FakeLLMOutput:
            explanation = "This finding relates to Section 16 eligibility conditions."

        chat_mock = AsyncMock(return_value=_FakeLLMOutput())
        monkeypatch.setattr(explain, "similarity_search", search_mock)
        monkeypatch.setattr(explain, "chat", chat_mock)

        result = await explain_finding(_finding(ReasonCode.EX_09))

        assert result is not None
        assert result.grounded is True
        assert result.explanation == "This finding relates to Section 16 eligibility conditions."
        assert len(result.citations) == 1
        assert result.citations[0].citation == retrieved[0].chunk.citation
        assert result.citations[0].score == retrieved[0].score

    @pytest.mark.asyncio
    async def test_retrieval_query_used_matches_the_fixed_mapping(self, monkeypatch) -> None:
        search_mock = AsyncMock(return_value=[_retrieved()])
        chat_mock = AsyncMock(return_value=type("Out", (), {"explanation": "x"})())
        monkeypatch.setattr(explain, "similarity_search", search_mock)
        monkeypatch.setattr(explain, "chat", chat_mock)

        await explain_finding(_finding(ReasonCode.EX_06))

        search_mock.assert_awaited_once()
        query_arg = search_mock.await_args.args[0]
        assert query_arg == RETRIEVAL_QUERIES[ReasonCode.EX_06]


class TestGenerationFailure:
    @pytest.mark.asyncio
    async def test_llm_failure_keeps_citations_but_falls_back(self, monkeypatch) -> None:
        retrieved = [_retrieved()]
        search_mock = AsyncMock(return_value=retrieved)
        chat_mock = AsyncMock(side_effect=openai.APIConnectionError(request=None))
        monkeypatch.setattr(explain, "similarity_search", search_mock)
        monkeypatch.setattr(explain, "chat", chat_mock)

        result = await explain_finding(_finding(ReasonCode.EX_04))

        assert result is not None
        assert result.grounded is False
        assert result.explanation == GENERATION_FAILED_MESSAGE
        # Citations from the already-successful retrieval are NOT discarded
        # just because the model call on top of them failed.
        assert len(result.citations) == 1


class TestBatch:
    @pytest.mark.asyncio
    async def test_explain_findings_preserves_order_and_handles_mixed_scope(
        self, monkeypatch
    ) -> None:
        search_mock = AsyncMock(return_value=[])
        monkeypatch.setattr(explain, "similarity_search", search_mock)

        findings = [
            _finding(ReasonCode.EX_09),  # in scope -> guardrail fallback
            _finding(ReasonCode.EX_02),  # out of scope -> None
            _finding(ReasonCode.EX_01),  # in scope -> guardrail fallback
        ]
        results = await explain_findings(findings, max_concurrency=2)

        assert len(results) == 3
        assert results[0] is not None and results[0].reason_code == ReasonCode.EX_09
        assert results[1] is None
        assert results[2] is not None and results[2].reason_code == ReasonCode.EX_01
