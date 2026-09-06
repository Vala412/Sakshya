"""Phase 3: retrieval-augmented explanation and chat layer over GST law.

Kept as a separate subpackage (with its own `rag` extras group in
pyproject.toml) so the deterministic Phase 1-2 engine never gains an OpenAI
SDK, a Qdrant client, or FastAPI as a hard dependency -- someone auditing
just the matching/classification logic shouldn't need any of them installed.
"""
