"""One shared AsyncOpenAI client for the whole rag package.

Both embeddings (retrieval-time) and chat completions (generation-time) are
the same OpenAI account and, in practice, the same underlying HTTP
connection pool -- there is no reason for `rag/retrieval/embeddings.py` and
`rag/generation/llm_client.py` to each hold their own client instance, and
every reason not to (two idle connection pools instead of one, two places
that could drift on client construction options).
"""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from gstrecon.rag.config import get_settings


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)
