"""OpenAI embeddings client: one string at query time, many at corpus-index
time.

Async throughout (not just here) because the chat interface (Phase 3's
other half, per project scope) needs to stream a response while retrieval
and generation calls are in flight -- building this synchronously now and
retrofitting async later, the way it's easy to defer, is exactly the kind
of decision that's expensive to undo once services.py/api/ exist on top of
it.
"""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from gstrecon.rag.config import get_settings


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


async def embed_text(text: str) -> list[float]:
    """Embed a single string (query time)."""
    return (await embed_batch([text]))[0]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed many strings in one request (corpus-index time).

    OpenAI's embeddings endpoint accepts up to 2048 inputs per request; the
    law corpus (a few hundred chunks) fits in a single call, so no
    batching-within-batching is implemented here. Add it if the corpus
    grows past that (e.g. IGST/UTGST Acts, notifications) -- premature now.
    """
    if not texts:
        return []
    response = await _client().embeddings.create(
        model=get_settings().openai_embedding_model, input=texts
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    return [item.embedding for item in ordered]
