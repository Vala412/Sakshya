"""Batch explanation generation: attach a citation and an LLM-written
explanation to already-classified exceptions.

This is the only place an LLM enters this project's decision path, and it
never gets to decide anything: the reason code, severity, and every number
in a finding were already fixed by the deterministic engine
(exceptions.py) before this module runs. The LLM's job is narrower than
"explain" -- given a citation this module has already decided is
trustworthy (the similarity floor, enforced in vector_store.py), write one
plain-English paragraph about it. If nothing trustworthy was found, the
LLM is never called at all; the fallback message is a constant, not
something the model is trusted to produce on request.
"""

from __future__ import annotations

import asyncio

import openai
from openai.types.responses.easy_input_message_param import EasyInputMessageParam
from pydantic import BaseModel, ConfigDict

from gstrecon.exceptions import Exception_, ReasonCode
from gstrecon.rag.generation.llm_client import chat
from gstrecon.rag.generation.prompts import RETRIEVAL_QUERIES, SYSTEM_PROMPT, build_user_message
from gstrecon.rag.retrieval.vector_store import similarity_search

NO_CITATION_MESSAGE = (
    "No supporting reference in the CGST Act/Rules corpus was found above "
    "the confidence threshold for this finding."
)
GENERATION_FAILED_MESSAGE = (
    "A citation was found but the explanation could not be generated "
    "(the language model call failed). See citations below and consult "
    "the cited section/rule directly."
)


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)

    citation: str
    score: float


class ExplanationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason_code: ReasonCode
    explanation: str
    citations: list[Citation]
    # False whenever `explanation` is a fallback constant rather than an
    # actual model-written, citation-grounded sentence -- callers (e.g. the
    # working-paper writer) should visually distinguish this rather than
    # present a fallback message as if it were a real explanation.
    grounded: bool


class _LLMOutput(BaseModel):
    explanation: str


async def explain_finding(finding: Exception_, *, top_k: int = 3) -> ExplanationResult | None:
    """Return an explanation for `finding`, or None if its reason code
    isn't in scope for explanation at all (see prompts.py's docstring:
    LOW-severity, zero-ITC-impact codes are excluded from
    RETRIEVAL_QUERIES on purpose, not by omission).
    """
    query = RETRIEVAL_QUERIES.get(finding.reason_code)
    if query is None:
        return None

    results = await similarity_search(query, top_k=top_k)
    if not results:
        return ExplanationResult(
            reason_code=finding.reason_code,
            explanation=NO_CITATION_MESSAGE,
            citations=[],
            grounded=False,
        )

    citations = [Citation(citation=r.chunk.citation, score=r.score) for r in results]
    user_message = build_user_message(
        reason_code=finding.reason_code,
        description=finding.description,
        evidence=finding.evidence,
        itc_at_risk=str(finding.itc_at_risk),
        excerpts=[(r.chunk.citation, r.chunk.text) for r in results],
    )

    try:
        llm_output = await chat(
            [
                EasyInputMessageParam(role="system", content=SYSTEM_PROMPT),
                EasyInputMessageParam(role="user", content=user_message),
            ],
            _LLMOutput,
        )
    except (openai.OpenAIError, ValueError):
        # A citation was already found and is worth keeping even if the
        # model call itself failed (rate limit, transient network error,
        # a malformed response that didn't fit the schema) -- one failed
        # generation shouldn't discard retrieval work that already
        # succeeded, and mustn't be allowed to sink the rest of the batch
        # (see explain_findings).
        return ExplanationResult(
            reason_code=finding.reason_code,
            explanation=GENERATION_FAILED_MESSAGE,
            citations=citations,
            grounded=False,
        )

    return ExplanationResult(
        reason_code=finding.reason_code,
        explanation=llm_output.explanation,
        citations=citations,
        grounded=True,
    )


async def explain_findings(
    findings: list[Exception_], *, max_concurrency: int = 5
) -> list[ExplanationResult | None]:
    """Explain many findings concurrently, capped at `max_concurrency` in
    flight -- a working paper with a large exception register shouldn't
    fire off one request per finding simultaneously and trip OpenAI's rate
    limits. Order matches `findings`; a None means that finding's reason
    code is out of scope (see explain_finding).
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _bounded(finding: Exception_) -> ExplanationResult | None:
        async with semaphore:
            return await explain_finding(finding)

    return await asyncio.gather(*(_bounded(f) for f in findings))
