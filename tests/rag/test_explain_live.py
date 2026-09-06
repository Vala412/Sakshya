"""Live integration test for the explanation layer: real Qdrant retrieval +
a real OpenAI chat call, end to end. Skipped if either isn't configured --
see test_vector_store.py's module docstring for the same pattern.

Costs one embedding call and one chat completion call per test (a fraction
of a cent) when it does run.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from gstrecon.exceptions import Exception_, ReasonCode, Severity
from gstrecon.matching import MatchCategory
from gstrecon.rag.generation.explain import explain_finding
from tests.rag.test_vector_store import _openai_key_configured, _qdrant_reachable

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (_qdrant_reachable() and _openai_key_configured()),
        reason="Qdrant not reachable or OPENAI_API_KEY not set",
    ),
]


def _finding(reason_code: ReasonCode, description: str, evidence: str) -> Exception_:
    return Exception_(
        reason_code=reason_code,
        severity=Severity.HIGH,
        description=description,
        match_category=MatchCategory.UNMATCHED,
        books_doc=None,
        gstr2b_doc=None,
        itc_at_risk=Decimal("18000.00"),
        evidence=evidence,
    )


class TestLiveExplanation:
    @pytest.mark.asyncio
    async def test_ex09_blocked_credit_finding_cites_section_17(self) -> None:
        finding = _finding(
            ReasonCode.EX_09,
            description="ITC flagged unavailable in 2B but claimed in books",
            evidence="2b itc_availability=N for gstr2b.json.b2b[0].inv[3]",
        )

        result = await explain_finding(finding)

        assert result is not None
        assert result.grounded is True
        assert result.explanation  # non-empty, model actually wrote something
        assert any("Section 17" in c.citation for c in result.citations)

    @pytest.mark.asyncio
    async def test_explanation_never_invents_a_specific_subsection(self) -> None:
        # Regression: an earlier prompt let the model write "Section 17(1)"
        # for an excerpt labelled only "Section 17" -- a specific,
        # falsifiable sub-section number it wasn't given and got wrong (the
        # blocked-credits list the excerpt contains is (5), not (1)). Run
        # several times since this is a generative, non-deterministic
        # call -- one clean run wouldn't rule out the model doing it again
        # under slightly different phrasing.
        finding = _finding(
            ReasonCode.EX_09,
            description="ITC flagged unavailable in 2B but claimed in books",
            evidence="2b itc_availability=N for gstr2b.json.b2b[0].inv[3]",
        )
        subsection_pattern = re.compile(r"[Ss]ection\s+\d+[A-Z]?\s*\(\d+\)")

        for _ in range(3):
            result = await explain_finding(finding)
            assert result is not None
            assert not subsection_pattern.search(result.explanation), (
                f"explanation invented a specific sub-section: {result.explanation!r}"
            )

    @pytest.mark.asyncio
    async def test_ex11_credit_note_finding_cites_a_relevant_section(self) -> None:
        finding = _finding(
            ReasonCode.EX_11,
            description="Credit note in 2B with no reversal in books",
            evidence="gstr2b=gstr2b.json.cdnr[0].nt[0]",
        )

        result = await explain_finding(finding)

        assert result is not None
        assert result.grounded is True
        assert len(result.citations) > 0
        # Every score must be above the configured floor -- similarity_search
        # already enforces this server-side, this just double-checks nothing
        # here bypasses it.
        from gstrecon.rag.config import get_settings

        floor = get_settings().similarity_floor
        assert all(c.score >= floor for c in result.citations)
