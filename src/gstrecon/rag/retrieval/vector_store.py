"""Qdrant wrapper for the GST law corpus: create the collection, upsert
chunked sections/rules, and run similarity search with the project's
citation-safety guardrail (a hard similarity floor) applied.
"""

from __future__ import annotations

import hashlib
import uuid
from functools import lru_cache

from pydantic import BaseModel, ConfigDict
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from gstrecon.rag.config import get_settings
from gstrecon.rag.corpus.chunker import LawChunk
from gstrecon.rag.retrieval.embeddings import embed_batch, embed_text


class RetrievedChunk(BaseModel):
    """A LawChunk plus how well it matched a specific query -- the score is
    query-dependent, so it doesn't belong on LawChunk itself."""

    model_config = ConfigDict(frozen=True)

    chunk: LawChunk
    score: float


@lru_cache(maxsize=1)
def _client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=get_settings().qdrant_url)


def _point_id(chunk: LawChunk) -> str:
    """Deterministic point ID from (source document, section number, part,
    content hash) so re-running the embed/upsert pipeline updates existing
    points in place rather than accumulating duplicates every time the
    corpus is re-ingested.

    `part` must be included: two pieces of an oversized section (see
    chunker.MAX_CHUNK_CHARS) share the same section_number, and omitting it
    would collapse them onto one point, silently dropping every part but
    the last one upserted.

    The content hash must *also* be included -- found as a real, silent
    data-loss bug, not a hypothetical: the real CGST Rules PDF quotes an
    old, pre-amendment version of rule 138/138B/138C/138D in full inside an
    inline footnote, so the chunker (correctly, given the text it's
    handed) produces two distinct chunks sharing the same section_number
    with different content. Without the hash, both were assigned the same
    point ID and the second upsert silently discarded the first's
    embedding -- verified by comparing the real embedded collection's
    point count (407) against the real chunk count (413) after a full
    corpus embed. The hash lets coincidentally-same-numbered but
    genuinely-different content coexist as separate points, while staying
    idempotent for the common case (identical content re-chunked the same
    way -> identical hash -> identical ID -> a clean overwrite, not a
    duplicate).
    """
    content_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()[:16]
    key = f"{chunk.source_document}:{chunk.section_number}:{chunk.part}:{content_hash}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, key))


async def ensure_collection() -> None:
    """Create the collection if it doesn't already exist. Never drops or
    recreates an existing one -- that's an explicit, separate operation
    (see `delete_collection` / scripts/embed_corpus.py's --force flag), not
    something a routine startup call should risk doing by accident."""
    settings = get_settings()
    client = _client()
    if await client.collection_exists(settings.qdrant_collection):
        return
    await client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qmodels.VectorParams(
            size=settings.embedding_dimensions, distance=qmodels.Distance.COSINE
        ),
    )


async def delete_collection() -> None:
    """Drop the collection entirely, if it exists. Destructive and explicit
    on purpose: `upsert_chunks` only ever adds or overwrites points by ID,
    it never removes ones that no longer correspond to a current chunk
    (e.g. after a chunking-boundary fix changes how many parts a section
    splits into) -- this is the actual way to clear that staleness, by
    starting the collection over from nothing rather than trying to diff
    old and new point sets."""
    settings = get_settings()
    client = _client()
    if await client.collection_exists(settings.qdrant_collection):
        await client.delete_collection(settings.qdrant_collection)


async def upsert_chunks(chunks: list[LawChunk]) -> int:
    """Embed and write `chunks`. Returns the number of points written."""
    if not chunks:
        return 0
    await ensure_collection()
    vectors = await embed_batch([chunk.text for chunk in chunks])
    points = [
        qmodels.PointStruct(
            id=_point_id(chunk),
            vector=vector,
            payload=chunk.model_dump(),
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    await _client().upsert(collection_name=get_settings().qdrant_collection, points=points)
    return len(points)


async def similarity_search(
    query: str,
    *,
    top_k: int = 5,
    score_threshold: float | None = None,
) -> list[RetrievedChunk]:
    """Return up to `top_k` chunks most relevant to `query`.

    `score_threshold` defaults to the configured similarity floor -- the
    project's hard citation-safety guardrail. Qdrant applies it server-side
    (candidates below the floor are never returned at all), so callers
    can't accidentally treat a below-floor match as a citation just by
    forgetting to check the score themselves.
    """
    settings = get_settings()
    threshold = settings.similarity_floor if score_threshold is None else score_threshold
    query_vector = await embed_text(query)
    response = await _client().query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        limit=top_k,
        score_threshold=threshold,
        with_payload=True,
    )
    return [
        RetrievedChunk(chunk=LawChunk(**hit.payload), score=hit.score)
        for hit in response.points
        if hit.payload is not None
    ]
