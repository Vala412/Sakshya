"""Typed settings for the RAG layer, loaded from environment variables / a
local .env file.

Kept separate from the deterministic Phase 1-2 engine, which has no
settings object at all: it has no external services to configure. This
exists only because Phase 3 talks to OpenAI and Qdrant, and a missing or
malformed credential should fail loudly at startup (pydantic-settings
validation) rather than deep inside an API call.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class RagSettings(BaseSettings):
    # ".env" is resolved relative to the process's current working
    # directory, not this file's location or a project root -- fine as
    # long as every entry point is run from the repo root (true of every
    # Makefile target and every documented `uv run ...` command in this
    # project), but would silently stop finding the file if that ever
    # changes (e.g. a script invoked via an absolute path from elsewhere).
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    # text-embedding-3-small's fixed output size (OpenAI's published spec,
    # not something to infer from a response at runtime) -- Qdrant needs
    # this when creating the collection, before any vector has been seen.
    embedding_dimensions: int = 1536

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "gst_law_corpus"

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Cosine-similarity floor below which a retrieved chunk isn't trustworthy
    # enough to cite -- the hard guardrail from the project roadmap: nothing
    # retrieved above this floor means the explanation layer must say "no
    # supporting reference located," never generate fluent prose without a
    # source.
    #
    # Calibrated empirically against the real embedded corpus via
    # scripts/test_retrieval.py, not guessed: six realistic GST queries
    # ("input tax credit blocked for motor vehicles", "reversal of input
    # tax credit when payment not made to supplier", etc.) returned top-5
    # scores of 0.47-0.72, all genuinely on-point citations. Three
    # deliberately unrelated queries ("recipe for chocolate cake", "how to
    # play chess") topped out at 0.09-0.13 against the same corpus. 0.30
    # sits in the wide, clean gap between those two clusters. Re-run that
    # script and revisit this constant if the corpus changes materially
    # (e.g. adding notifications or a second Act).
    similarity_floor: float = 0.30


@lru_cache(maxsize=1)
def get_settings() -> RagSettings:
    return RagSettings()  # type: ignore[call-arg]  # openai_api_key comes from env/.env
